#!/usr/bin/env python3
from __future__ import print_function

import json
import os
import shutil
import tempfile
import threading
import time
from urllib.parse import quote

from openaps_locald.authorization_protocol import build_enrollment_record
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.nightscout_authorization import (
    NightscoutAuthorizationError,
    NightscoutDeviceAuthorizationClient,
    URLTransport,
    _decode_jwt_payload,
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def client_for(root, name, url, token, wallclock=None):
    identity = DeviceIdentity(os.path.join(root, name + "-identity"))
    client = NightscoutDeviceAuthorizationClient(
        url,
        token,
        identity,
        "rig",
        os.path.join(root, name + "-trust.json"),
        wallclock=wallclock,
    )
    return client


def concurrent_create_probe(root, url, token, server_date, attempts=32, rounds=5):
    for round_index in range(rounds):
        client = client_for(root, "race-%d" % round_index, url, token)
        body = build_enrollment_record(
            client.identity,
            "rig",
            client.base_url,
            server_date,
        )
        path = client._exact_path(client.identity.credential_id)
        barrier = threading.Barrier(attempts)
        results = []
        failures = []
        result_lock = threading.Lock()

        def create_once():
            try:
                barrier.wait()
                status, _payload = client._authenticated_request(
                    "PUT", path, body=body
                )
                with result_lock:
                    results.append(status)
            except Exception as exc:
                with result_lock:
                    failures.append(type(exc).__name__)

        workers = [threading.Thread(target=create_once) for _ in range(attempts)]
        for worker in workers:
            worker.daemon = True
            worker.start()
        for worker in workers:
            worker.join(30)
        require(not any(worker.is_alive() for worker in workers),
                "concurrent PUT workers did not finish")
        duplicate_state = client.duplicate_audit(client.identity.credential_id)
        if duplicate_state == "multiple_live":
            return {
                "duplicate_state": duplicate_state,
                "round": round_index + 1,
                "statuses": sorted(results),
                "failures": sorted(failures),
            }
    raise AssertionError(
        "concurrent PUT probe did not expose duplicate live identifiers"
    )


def auto_prune_probe(root, regular_url, prune_url, token, server_date):
    regular_live = client_for(root, "old-live", regular_url, token)
    regular_tombstone = client_for(root, "old-tombstone", regular_url, token)
    old_date = server_date - (2 * 24 * 60 * 60 * 1000)

    for client in (regular_live, regular_tombstone):
        body = build_enrollment_record(
            client.identity, "rig", client.base_url, old_date
        )
        status, _payload = client._authenticated_request(
            "PUT", client._exact_path(client.identity.credential_id), body=body
        )
        require(status == 201, "non-pruning setup PUT failed")

    delete_status, _payload = regular_tombstone._authenticated_request(
        "DELETE",
        regular_tombstone._exact_path(regular_tombstone.identity.credential_id),
    )
    require(delete_status == 200, "non-pruning setup DELETE failed")
    live_before, _payload = regular_live.exact_lookup(
        regular_live.identity.credential_id
    )
    tombstone_before, _payload = regular_tombstone.exact_lookup(
        regular_tombstone.identity.credential_id
    )
    require(live_before == "present",
            "no-auto-prune server removed an old live record")
    require(tombstone_before == "candidate_revoked",
            "no-auto-prune server removed an old tombstone")

    trigger = client_for(root, "prune-trigger", prune_url, token)
    trigger_status = trigger.status()
    trigger_body = build_enrollment_record(
        trigger.identity, "rig", trigger.base_url, trigger_status["srvDate"]
    )
    status, _payload = trigger._authenticated_request(
        "PUT", trigger._exact_path(trigger.identity.credential_id),
        body=trigger_body,
    )
    require(status == 201, "auto-prune trigger PUT failed")

    live_after = None
    tombstone_after = None
    for _attempt in range(50):
        live_after, _payload = trigger.exact_lookup(
            regular_live.identity.credential_id
        )
        tombstone_after, _payload = trigger.exact_lookup(
            regular_tombstone.identity.credential_id
        )
        if live_after == "absent" and tombstone_after == "absent":
            break
        time.sleep(0.1)
    require(live_after == "absent",
            "auto-prune did not hard-delete the old live record")
    require(tombstone_after == "absent",
            "auto-prune did not hard-delete the old tombstone")
    return "passed"


def ambiguous_timeout_restart_probe(root, url, token):
    """Lose a real create response and readback, then recover after restart.

    The first client deliberately treats the server's successful PUT response
    and its one permitted exact readback as transport failures.  The next
    process must discover the server-stored record without attempting another
    non-atomic PUT.
    """
    identity_path = os.path.join(root, "ambiguous-live-identity")
    state_path = os.path.join(root, "ambiguous-live-trust.json")
    identity = DeviceIdentity(identity_path)
    target = "/api/v3/devicestatus/" + identity.credential_id
    # The client transforms the raw credential id into its registry identifier
    # internally, so use its path helper instead of reconstructing the prefix.
    path_client = NightscoutDeviceAuthorizationClient(
        url, token, identity, "rig", state_path
    )
    target = path_client._exact_path(identity.credential_id)

    class LostCreateResponseTransport(object):
        def __init__(self, delegate, exact_path):
            self.delegate = delegate
            self.exact_path = exact_path
            self.exact_reads = 0
            self.puts = 0

        def request(self, method, path, body=None, bearer=None, query=None,
                    api_secret=None):
            if method == "GET" and path == self.exact_path:
                self.exact_reads += 1
                if self.exact_reads == 2:
                    raise NightscoutAuthorizationError("network")
            status, payload = self.delegate.request(
                method, path, body=body, bearer=bearer, query=query,
                api_secret=api_secret,
            )
            if method == "PUT" and path == self.exact_path:
                self.puts += 1
                if self.puts == 1:
                    raise NightscoutAuthorizationError("network")
            return status, payload

    dropped = LostCreateResponseTransport(URLTransport(url), target)
    first = NightscoutDeviceAuthorizationClient(
        url, token, identity, "rig", state_path, transport=dropped
    )
    first_state = first.reconcile_self()
    require(first_state.get("classification") == "ambiguous_create",
            "lost create response did not leave a durable ambiguous state")
    require(dropped.puts == 1 and dropped.exact_reads == 2,
            "ambiguous create did not use exactly one PUT and readback")

    class CountingTransport(object):
        def __init__(self, delegate):
            self.delegate = delegate
            self.requests = []

        def request(self, method, path, body=None, bearer=None, query=None,
                    api_secret=None):
            self.requests.append((method, path))
            return self.delegate.request(
                method, path, body=body, bearer=bearer, query=query,
                api_secret=api_secret,
            )

    restarted_transport = CountingTransport(URLTransport(url))
    restarted_identity = DeviceIdentity(identity_path)
    restarted = NightscoutDeviceAuthorizationClient(
        url, token, restarted_identity, "rig", state_path,
        transport=restarted_transport,
    )
    recovered = restarted.reconcile_self()
    require(recovered.get("classification") == "present",
            "restart did not recover the server-stored enrollment")
    require(recovered.get("duplicate_state") == "one_live_non_authoritative",
            "restart recovery did not retain exactly one live enrollment")
    require(not any(
        method == "PUT" and path == target
        for method, path in restarted_transport.requests
    ), "restart retried a non-atomic enrollment PUT")
    return "passed"


def main():
    url = os.environ.get("OPENAPS_NS_LAB_URL")
    insecure_url = os.environ.get("OPENAPS_NS_INSECURE_LAB_URL")
    prune_url = os.environ.get("OPENAPS_NS_PRUNE_LAB_URL")
    token = os.environ.get("OPENAPS_NS_LAB_TOKEN")
    read_only_token = os.environ.get("OPENAPS_NS_LAB_READ_ONLY_TOKEN")
    require(url and token and read_only_token,
            "set OPENAPS_NS_LAB_URL, OPENAPS_NS_LAB_TOKEN, and "
            "OPENAPS_NS_LAB_READ_ONLY_TOKEN")

    root = tempfile.mkdtemp(prefix="openaps-nightscout-live-")
    try:
        bad_clock_client = client_for(
            root, "bad-clock", url, token, wallclock=lambda: 0
        )
        exchange_status, exchange = bad_clock_client.transport.request(
            "GET", "/api/v2/authorization/request/" + quote(token, safe="")
        )
        require(exchange_status == 200 and isinstance(exchange, dict),
                "JWT exchange did not return an object")
        require(all(key in exchange for key in ("token", "iat", "exp", "sub")),
                "JWT exchange omitted pinned top-level fields")
        claims = _decode_jwt_payload(exchange["token"])
        require(claims.get("accessToken") == token,
                "JWT accessToken claim did not bind the configured token")
        require(exchange["iat"] == claims.get("iat"),
                "JWT envelope iat did not match compact claims")
        require(exchange["exp"] == claims.get("exp"),
                "JWT envelope exp did not match compact claims")

        status = bad_clock_client.status()
        require(status.get("srvDate", 0) > 0, "missing authenticated server time")

        capability = bad_clock_client.capability_probe()
        require(capability.get("security_enabled"),
                "unauthenticated API-v3 PUT was not rejected")
        require(capability.get("supported") and capability.get("read"),
                "authorized capability ordering/read probe failed")
        require(capability.get("create"),
                "create-capable token was not recognized")

        read_only = client_for(
            root, "read-only", url, "token=" + read_only_token
        )
        read_only_capability = read_only.capability_probe()
        require(read_only_capability.get("supported"),
                "read-only capability ordering probe was inconclusive")
        require(read_only_capability.get("read"),
                "read-only token could not read devicestatus")
        require(not read_only_capability.get("create"),
                "read-only token unexpectedly received create permission")

        insecure_probe = "not_requested"
        if insecure_url:
            insecure = client_for(
                root, "security-disabled", insecure_url, "placeholder-token"
            )
            insecure_capability = insecure.capability_probe()
            require(not insecure_capability.get("supported"),
                    "security-disabled Nightscout was accepted")
            require(not insecure_capability.get("security_enabled"),
                    "security-disabled Nightscout was misclassified")
            insecure_probe = "passed"

        first = bad_clock_client.reconcile_self()
        require(first.get("classification") == "present",
                "self enrollment did not reconcile present")
        require(bad_clock_client.carrier_ready(),
                "validated self enrollment did not make the shadow carrier ready")
        require(first.get("last_registry_srv_created", 0) > 0,
                "self enrollment did not persist srvCreated")
        require(first.get("last_registry_srv_modified", 0) > 0,
                "self enrollment did not persist srvModified")

        classification, document = bad_clock_client.exact_lookup(
            bad_clock_client.identity.credential_id
        )
        require(classification == "present", "exact self lookup failed")
        require(abs(document.get("date") - status["srvDate"]) < 60000,
                "enrollment used the bad local wall clock instead of server time")
        original_created = document.get("srvCreated")
        original_modified = document.get("srvModified")

        second = bad_clock_client.reconcile_self()
        require(second.get("classification") == "present",
                "existing self record stopped reconciling")
        _classification, unchanged = bad_clock_client.exact_lookup(
            bad_clock_client.identity.credential_id
        )
        require(unchanged.get("srvCreated") == original_created,
                "existing enrollment was recreated or updated")
        require(unchanged.get("srvModified") == original_modified,
                "existing enrollment was unexpectedly modified")

        unknown = "0" * 64
        unknown_result = bad_clock_client.lookup_peer(unknown, "phone")
        require(unknown_result.get("classification") == "absent",
                "unknown peer was not classified as absent")
        cached_result = bad_clock_client.lookup_peer(unknown, "phone")
        require(cached_result.get("classification") == "negative_cached",
                "unknown peer negative result was not cached")

        delete_status, _payload = bad_clock_client._authenticated_request(
            "DELETE",
            bad_clock_client._exact_path(bad_clock_client.identity.credential_id),
        )
        require(delete_status == 200, "soft DELETE did not succeed")
        revoked, _document = bad_clock_client.exact_lookup(
            bad_clock_client.identity.credential_id
        )
        require(revoked == "candidate_revoked",
                "soft-deleted enrollment did not return 410")
        replacement = build_enrollment_record(
            bad_clock_client.identity,
            "rig",
            bad_clock_client.base_url,
            bad_clock_client.status()["srvDate"],
        )
        replacement_status, _payload = bad_clock_client._authenticated_request(
            "PUT",
            bad_clock_client._exact_path(bad_clock_client.identity.credential_id),
            body=replacement,
        )
        require(replacement_status == 410,
                "PUT unexpectedly revived a soft-deleted enrollment")

        ambiguous_result = ambiguous_timeout_restart_probe(root, url, token)

        race = concurrent_create_probe(
            root, url, token, status["srvDate"]
        )
        prune_result = "not_requested"
        if prune_url:
            prune_result = auto_prune_probe(
                root, url, prune_url, token, status["srvDate"]
            )

        print(json.dumps({
            "bad_clock_server_time": "passed",
            "capability_probe": "passed",
            "read_only_probe": "passed",
            "security_disabled_rejection": insecure_probe,
            "jwt_envelope_and_claims": "passed",
            "token_prefix_normalization": "passed",
            "enrollment_readback": "passed",
            "existing_record_no_update": "passed",
            "unknown_peer_404": "passed",
            "soft_delete_410": "passed",
            "soft_deleted_put_410": "passed",
            "ambiguous_timeout_restart_recovery": ambiguous_result,
            "concurrent_put": race,
            "auto_prune_live_and_tombstone": prune_result,
        }, sort_keys=True, indent=2))
        return 0
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    raise SystemExit(main())
