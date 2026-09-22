from __future__ import print_function

import base64
import fcntl
import json
import multiprocessing
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
try:
    from http.client import HTTPConnection
    from http.server import HTTPServer
except ImportError:
    from httplib import HTTPConnection
    from BaseHTTPServer import HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from openaps_locald.authorization_protocol import (
    AUTH_HELLO_SCHEMA,
    BLE_AUTH_ATTEMPT_CAPACITY,
    BLE_AUTH_ATTEMPT_REFILL_SECONDS,
    BLE_CREDENTIAL_ATTEMPT_CAPACITY,
    BLE_CREDENTIAL_REFILL_SECONDS,
    BLE_MAX_SESSIONS_GLOBAL,
    BLE_MAX_SESSIONS_PER_CREDENTIAL,
    BLE_UNKNOWN_CREDENTIAL_LIMIT,
    HTTP_AUTH_ATTEMPT_CAPACITY,
    HTTP_AUTH_ATTEMPT_REFILL_SECONDS,
    HTTP_CREDENTIAL_ATTEMPT_CAPACITY,
    HTTP_CREDENTIAL_REFILL_SECONDS,
    HTTP_MAX_SESSIONS_GLOBAL,
    HTTP_MAX_SESSIONS_PER_CREDENTIAL,
    HTTP_UNKNOWN_CREDENTIAL_LIMIT,
    LEGACY_V1_AUTHENTICATED_CARRIER,
    MAX_AUTH_CHUNKS,
    MAX_AUTH_MESSAGE_BYTES,
    AuthorizationError,
    ChallengeStore,
    SessionStore,
    ack_transcript,
    auth_ack_transcript,
    auth_hello_transcript,
    build_auth_ack,
    build_auth_hello,
    build_enrollment_record,
    build_signed_ack,
    build_signed_event,
    continuity_is_stale,
    enrollment_transcript,
    event_transcript,
    realm_id_for_nightscout,
    registry_identifier,
    validate_auth_hello_shape,
    validate_enrollment_document,
    validate_signed_ack,
    validate_signed_event,
    verify_auth_ack,
    verify_auth_hello,
)
from openaps_locald.device_identity import (
    DeviceIdentity,
    IdentityError,
    credential_id_for_public_key,
    validate_signature_der,
)
from openaps_locald.nightscout_authorization import (
    JWT_BACKOFF_SECONDS,
    NightscoutAuthorizationError,
    NightscoutDeviceAuthorizationClient,
    ShadowTrustStore,
    TemporaryJWTProvider,
)
import openaps_locald.nightscout_authorization as nightscout_authorization_module
from openaps_locald.http_api import ThreadedHTTPServer, make_handler
from openaps_locald.authorization_runtime import AuthorizationRuntime
import openaps_locald.authorization_runtime as authorization_runtime_module
from openaps_locald.authorization_replay import (
    AuthorizationReplayError,
    AuthorizationReplayStore,
)
import openaps_locald.ble_server as ble_server_module
from openaps_locald.ble_server import BLUEZ_DEVICE_IFACE, Characteristic, RigBridge
from openaps_locald.ble_protocol import BLE_ACK_CHAR_UUID, BleChunkAssembler, BleProtocolError


class FakeClock(object):
    def __init__(self, value=1000.0):
        self.value = float(value)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class InMemoryReplay(object):
    def __init__(self):
        self.entries = set()
        self.lock = threading.Lock()

    def consume(self, kind, credential_id, message_id, ack_digest=None):
        key = (kind, credential_id, message_id, ack_digest or "")
        with self.lock:
            if key in self.entries:
                raise AuthorizationError("authorization message was replayed")
            self.entries.add(key)
        return True


def compact_jwt(access_token, iat, exp, signature_suffix="1"):
    def segment(value):
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")

    signature = base64.urlsafe_b64encode(
        ("signature-" + signature_suffix).encode("ascii")
    ).decode("ascii").rstrip("=")
    return ".".join([
        segment({"alg": "HS256", "typ": "JWT"}),
        segment({"accessToken": access_token, "iat": iat, "exp": exp}),
        signature,
    ])


class AuthorizationTransport(object):
    def __init__(
        self,
        identity=None,
        security_enabled=True,
        create_allowed=True,
        compact_lifetime_only=False,
        create_outcome="success",
        create_last_modified=1893553445000,
        server_date=1893553445000,
    ):
        self.identity = identity
        self.security_enabled = security_enabled
        self.create_allowed = create_allowed
        self.exchange_count = 0
        self.requests = []
        self.documents = {}
        self.subject = "subject-placeholder"
        self.force_one_401 = False
        self.compact_lifetime_only = compact_lifetime_only
        self.create_outcome = create_outcome
        self.create_last_modified = create_last_modified
        self.server_date = server_date

    def request(self, method, path, body=None, bearer=None, query=None):
        self.requests.append((method, path, body, bearer, query))
        if path.startswith("/api/v2/authorization/request/"):
            self.exchange_count += 1
            response = {
                # Nightscout's response includes these values at top level at
                # the pinned version. Omitting iat/exp here proves the client
                # also handles deployments that only return the compact JWT.
                "token": compact_jwt(
                    "access-placeholder",
                    10,
                    10 + 8 * 60 * 60,
                    str(self.exchange_count),
                ),
                "sub": self.subject,
            }
            if not self.compact_lifetime_only:
                response["iat"] = 10
                response["exp"] = 10 + 8 * 60 * 60
            return 200, response
        if self.force_one_401 and bearer and path == "/api/v3/status":
            self.force_one_401 = False
            return 401, {"status": 401}
        if path == "/api/v3/status":
            return 200, {"status": 200, "result": {"srvDate": self.server_date}}
        if path == "/api/v3/devicestatus" and method == "GET":
            identifier = (query or {}).get("identifier$eq")
            result = [value for key, value in self.documents.items() if key == identifier]
            return 200, {"status": 200, "result": result}
        prefix = "/api/v3/devicestatus/"
        if path.startswith(prefix):
            identifier = path[len(prefix):]
            is_probe = identifier.startswith("openaps-auth-capability-probe-")
            if method == "PUT" and not bearer:
                return (401 if self.security_enabled else 400), {"status": 401 if self.security_enabled else 400}
            if method == "GET":
                document = self.documents.get(identifier)
                if document is None:
                    return 404, {"status": 404}
                return 200, {"status": 200, "result": document}
            if method == "PUT" and is_probe:
                return (400 if self.create_allowed else 403), {"status": 400 if self.create_allowed else 403}
            if method == "PUT":
                if not self.create_allowed:
                    return 403, {"status": 403}
                if self.create_outcome == "network_without_store":
                    raise NightscoutAuthorizationError("network")
                document = dict(body)
                document["identifier"] = identifier
                document["subject"] = self.subject
                document["srvCreated"] = 1893553445000
                document["srvModified"] = 1893553445000
                self.documents[identifier] = document
                if self.create_outcome == "definitive_500":
                    return 500, {"status": 500}
                if self.create_outcome == "network_after_store":
                    raise NightscoutAuthorizationError("network")
                if self.create_outcome == "nested_result":
                    return 201, {
                        "status": 201,
                        "result": {
                            "status": 201,
                            "identifier": identifier,
                            "lastModified": 1893553445000,
                        },
                    }
                return 201, {
                    "status": 201,
                    "identifier": identifier,
                    "lastModified": self.create_last_modified,
                }
        return 500, {"status": 500}


class LegacyAPISecretAuthorizationTransport(object):
    def __init__(self, probe_status=400, unauthenticated_probe_status=401):
        self.requests = []
        self.documents = []
        self.server_date = 1893553445000
        self.probe_status = probe_status
        self.unauthenticated_probe_status = unauthenticated_probe_status

    def request(self, method, path, body=None, bearer=None, query=None, api_secret=None):
        self.requests.append((method, path, body, bool(api_secret), query))
        if path == "/api/v1/status.json":
            if not api_secret:
                return 401, {"status": 401}
            return 200, {
                "status": "ok",
                "serverTime": "2030-01-01T01:44:05.000Z",
                "serverTimeEpoch": self.server_date,
            }
        if path in ("/api/v1/devicestatus/", "/api/v1/devicestatus.json"):
            if method == "POST" and not api_secret:
                return self.unauthenticated_probe_status, {
                    "status": self.unauthenticated_probe_status,
                }
            if method == "POST" and body and body.get("_id") == "invalid-openaps-auth-probe":
                return self.probe_status, {"status": self.probe_status}
            if method == "POST":
                document = dict(body)
                self.documents.append(document)
                return 200, [document]
            if method == "GET":
                identifier = (query or {}).get("find[identifier]")
                return 200, [
                    item for item in self.documents
                    if item.get("identifier") == identifier
                ][:int((query or {}).get("count") or 10)]
        raise AssertionError("unexpected legacy request: %s %s" % (method, path))


def _cross_process_record_peer(
    path,
    peer,
    authority_context_id,
    identity_directory,
    ready,
    start,
    done,
):
    identity = DeviceIdentity(identity_directory)
    store = ShadowTrustStore(
        path,
        authority_context_id=authority_context_id,
        local_credential_id=identity.credential_id,
        local_device_kind="rig",
        identity=identity,
    )
    ready.set()
    if not start.wait(10):
        raise RuntimeError("peer writer start timed out")
    store.record_peer_confirmation(
        peer,
        "one_live_non_authoritative",
        authority_context_id=authority_context_id,
    )
    done.set()


def _cross_process_record_self(
    path,
    state,
    authority_context_id,
    identity_directory,
    ready,
    peer_done,
):
    identity = DeviceIdentity(identity_directory)
    store = ShadowTrustStore(
        path,
        authority_context_id=authority_context_id,
        local_credential_id=identity.credential_id,
        local_device_kind="rig",
        identity=identity,
    )
    ready.set()
    if not peer_done.wait(10):
        raise RuntimeError("self writer peer wait timed out")
    store.record_self(state)


class DeviceAuthorizationTests(unittest.TestCase):
    def test_p256_credential_vector_matches_ios_protocol(self):
        public_key_der = bytes.fromhex(
            "3059301306072a8648ce3d020106082a8648ce3d03010703420004"
            "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
            "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5"
        )
        self.assertEqual(len(public_key_der), 91)
        self.assertEqual(
            credential_id_for_public_key(public_key_der),
            "ca9a7b2aba1560c5c498808e0024db57b0afe04fed9591aaf913cdeb3683a9c1",
        )

    def test_committed_cross_language_authorization_vectors(self):
        fixture_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "fixtures",
            "device-authorization-vectors.json",
        )
        with open(fixture_path, "r") as handle:
            fixture = json.load(handle)
        self.assertEqual(
            fixture.get("schema"),
            "openaps.device-authorization.test-vectors.v1",
        )
        self.assertEqual(len(fixture["vectors"]), 5)
        for vector in fixture["vectors"]:
            message_type = vector["message_type"]
            message = dict(vector["message"])
            public_key_der = base64.b64decode(vector["public_key_der"])
            signature_der = base64.b64decode(vector["signature_der"])
            self.assertEqual(
                credential_id_for_public_key(public_key_der),
                vector["credential_id"],
                message_type,
            )
            validate_signature_der(signature_der)

            if message_type == "enrollment":
                transcript = enrollment_transcript(
                    message["identifier"],
                    message["credential_id"],
                    message["device_kind"],
                    message["signing_public_key"],
                    message["record_sequence"],
                    message["record_nonce"],
                )
            elif message_type == "auth_hello":
                transcript = auth_hello_transcript(message)
            elif message_type == "auth_ack":
                transcript = auth_ack_transcript(message)
            elif message_type == "signed_event":
                transcript = event_transcript(message)
            elif message_type == "signed_ack":
                transcript = ack_transcript(message)
            else:
                self.fail("unexpected vector type %s" % message_type)

            self.assertEqual(
                transcript,
                base64.b64decode(vector["transcript_base64"]),
                message_type,
            )
            self.assertTrue(
                self.rig_identity.verify(
                    transcript,
                    signature_der,
                    vector["credential_id"],
                    public_key_der,
                ),
                message_type,
            )

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="openaps-auth-tests-")
        self.rig_identity = DeviceIdentity(os.path.join(self.tmp, "rig"))
        self.phone_identity = DeviceIdentity(os.path.join(self.tmp, "phone"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_ble_post_event_keeps_a_bounded_materialization_budget(self):
        class LegacyRuntime(object):
            @staticmethod
            def start_periodic_reconciliation():
                return None

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=LegacyRuntime())
        observed = {}

        class Response(object):
            @staticmethod
            def read():
                return b'{"acks":[{"ack_status":"stored","event_id":"event-placeholder"}]}'

        def fake_urlopen(_request, timeout):
            observed["timeout"] = timeout
            return Response()

        original_urlopen = ble_server_module.urlopen
        ble_server_module.urlopen = fake_urlopen
        try:
            ack = bridge.post_event({"event_id": "event-placeholder"})
        finally:
            ble_server_module.urlopen = original_urlopen

        self.assertEqual(observed["timeout"], 20)
        self.assertEqual(ack["event_id"], "event-placeholder")

    def _scoped_trust_store(self, path, authority_context_id, identity=None, device_kind="rig"):
        identity = identity or self.rig_identity
        return ShadowTrustStore(
            path,
            authority_context_id=authority_context_id,
            local_credential_id=identity.credential_id,
            local_device_kind=device_kind,
            identity=identity,
        )

    def _persisted_peer_record(self, authority_context_id, identity=None):
        identity = identity or self.phone_identity
        return {
            "credential_id": identity.credential_id,
            "device_kind": "phone",
            "authority_context_id": authority_context_id,
            "realm_id": authority_context_id,
            "registry_identifier": registry_identifier(identity.credential_id),
            "public_key_der": base64.b64encode(identity.public_key_der).decode("ascii"),
            "nightscout_subject": "subject-placeholder",
            "first_nightscout_confirmed_at": 1000.0,
            "last_nightscout_confirmed_at": 1001.0,
            "last_direct_contact_at": 1002.0,
            "last_registry_check_at": 1003.0,
            "last_registry_srv_created": 1893553445000,
            "last_registry_srv_modified": 1893553445001,
            "registry_duplicate_state": "one_live_non_authoritative",
            "candidate_revocation": {
                "observed_at": 1004.0,
                "evidence": "api-v3-selected-410",
                "authoritative": False,
            },
            "protocol_version": 1,
        }

    def _legacy_self_state(self, authority_context_id):
        return {
            "mode": "shadow",
            "credential_id": self.rig_identity.credential_id,
            "authority_context_id": authority_context_id,
            "capability": {
                "supported": True,
                "security_enabled": True,
                "read": True,
                "create": True,
            },
            "classification": "present",
            "duplicate_state": "one_live_non_authoritative",
            "last_attempt_at": 1000.0,
            "last_success_at": 1001.0,
            "last_registry_srv_created": 1893553445000,
            "last_registry_srv_modified": 1893553445001,
            "candidate_revocation": False,
        }

    def test_identity_is_persistent_private_and_strict_der(self):
        first_credential = self.rig_identity.credential_id
        reloaded = DeviceIdentity(os.path.join(self.tmp, "rig"))
        self.assertEqual(reloaded.credential_id, first_credential)
        self.assertEqual(
            stat.S_IMODE(os.stat(reloaded.private_key_path).st_mode),
            0o600,
        )
        self.assertEqual(
            credential_id_for_public_key(reloaded.public_key_der),
            first_credential,
        )
        message = b"placeholder authorization transcript"
        signature = reloaded.sign(message)
        self.assertTrue(
            self.phone_identity.verify(
                message,
                signature,
                first_credential,
                reloaded.public_key_der,
            )
        )
        with self.assertRaises(IdentityError):
            validate_signature_der(signature + b"\x00")
        self.assertFalse(
            self.phone_identity.verify(
                message + b"!",
                signature,
                first_credential,
                reloaded.public_key_der,
            )
        )

    def test_record_proof_and_realm_are_canonical(self):
        self.assertEqual(
            realm_id_for_nightscout("HTTPS://DIYPS.example.invalid:443/path?token=placeholder"),
            realm_id_for_nightscout("https://diyps.example.invalid"),
        )
        record = build_enrollment_record(
            self.phone_identity,
            "phone",
            "https://diyps.example.invalid",
            1893553445000,
            nonce=b"r" * 32,
        )
        self.assertNotIn("identifier", record)
        document = dict(record)
        document.update({
            "identifier": registry_identifier(self.phone_identity.credential_id),
            "subject": "subject-placeholder",
            "srvCreated": 1893553445000,
            "srvModified": 1893553445000,
        })
        validated = validate_enrollment_document(
            document,
            self.phone_identity.credential_id,
            "phone",
            self.rig_identity,
        )
        self.assertEqual(validated["public_key_der"], self.phone_identity.public_key_der)
        corrupted = json.loads(json.dumps(document))
        corrupted["openaps_auth"]["record_sequence"] = 2
        with self.assertRaises(AuthorizationError):
            validate_enrollment_document(
                corrupted,
                self.phone_identity.credential_id,
                "phone",
                self.rig_identity,
            )

    def test_enrollment_date_requires_a_positive_integral_timestamp(self):
        record = build_enrollment_record(
            self.phone_identity,
            "phone",
            "https://diyps.example.invalid",
            1893553445000,
            nonce=b"d" * 32,
        )
        document = dict(record)
        document.update({
            "identifier": registry_identifier(self.phone_identity.credential_id),
            "subject": "subject-placeholder",
            "srvCreated": 1893553445000,
            "srvModified": 1893553445000,
        })
        integral_float = json.loads(json.dumps(document))
        integral_float["date"] = 1.0
        validate_enrollment_document(
            integral_float,
            self.phone_identity.credential_id,
            "phone",
            self.rig_identity,
        )
        for invalid_date in (0, -1, 1.5, True, float("inf")):
            with self.subTest(date=invalid_date):
                malformed = json.loads(json.dumps(document))
                malformed["date"] = invalid_date
                with self.assertRaises(AuthorizationError):
                    validate_enrollment_document(
                        malformed,
                        self.phone_identity.credential_id,
                        "phone",
                        self.rig_identity,
                    )

    def test_enrollment_server_metadata_requires_positive_integral_timestamps(self):
        record = build_enrollment_record(
            self.phone_identity,
            "phone",
            "https://diyps.example.invalid",
            1893553445000,
            nonce=b"m" * 32,
        )
        document = dict(record)
        document.update({
            "identifier": registry_identifier(self.phone_identity.credential_id),
            "subject": "subject-placeholder",
            "srvCreated": 1.0,
            "srvModified": 2.0,
        })
        validated = validate_enrollment_document(
            document,
            self.phone_identity.credential_id,
            "phone",
            self.rig_identity,
        )
        self.assertEqual(validated["srv_created"], 1.0)
        self.assertEqual(validated["srv_modified"], 2.0)
        for field in ("srvCreated", "srvModified"):
            for invalid in (None, 0, -1, 1.5, True, float("inf")):
                with self.subTest(field=field, value=invalid):
                    malformed = dict(document)
                    malformed[field] = invalid
                    with self.assertRaises(AuthorizationError):
                        validate_enrollment_document(
                            malformed,
                            self.phone_identity.credential_id,
                            "phone",
                            self.rig_identity,
                        )

    def test_mutual_auth_and_signed_event_ack_round_trip(self):
        rig_challenge = "cnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnI="
        hello = build_auth_hello(
            self.phone_identity,
            self.rig_identity.credential_id,
            rig_challenge,
            phone_challenge=b"p" * 32,
            message_id="11111111-1111-4111-8111-111111111111",
        )
        self.assertIn(b"\n1\n", auth_hello_transcript(hello))
        malformed_hello = dict(hello)
        malformed_hello.pop("signature")
        with self.assertRaises(AuthorizationError):
            validate_auth_hello_shape(malformed_hello)
        verify_auth_hello(
            hello,
            self.rig_identity.credential_id,
            self.phone_identity.public_key_der,
            self.rig_identity,
        )
        ack = build_auth_ack(
            self.rig_identity,
            hello,
            session_id="22222222-2222-4222-8222-222222222222",
        )
        self.assertIn(b"\n1\n", auth_ack_transcript(ack))
        verify_auth_ack(
            ack,
            hello,
            self.rig_identity.public_key_der,
            self.phone_identity,
        )

        event_bytes = b'{"event_id":"evt-placeholder","schema":"openaps.local.event.v1"}'
        ack_bytes = b'{"ack_status":"stored","event_id":"evt-placeholder"}'
        signed_event = build_signed_event(
            self.phone_identity,
            ack["session_id"],
            self.rig_identity.credential_id,
            "evt-placeholder",
            event_bytes,
            ack_bytes,
            nonce=b"n" * 32,
        )
        self.assertEqual(
            validate_signed_event(
                signed_event,
                self.phone_identity.public_key_der,
                self.rig_identity,
            ),
            event_bytes,
        )
        signed_ack = build_signed_ack(
            self.rig_identity,
            ack["session_id"],
            self.phone_identity.credential_id,
            "evt-placeholder",
            signed_event["message_nonce"],
            ack_bytes,
        )
        self.assertIn(b"\n1\n", ack_transcript(signed_ack))
        self.assertEqual(
            validate_signed_ack(
                signed_ack,
                self.rig_identity.public_key_der,
                self.phone_identity,
            ),
            ack_bytes,
        )

    def test_challenge_session_replay_and_continuity(self):
        clock = FakeClock()
        challenges = ChallengeStore(monotonic=clock)
        challenge = challenges.issue("connection-placeholder")
        challenges.validate("connection-placeholder", challenge)
        challenges.consume("connection-placeholder", challenge)
        with self.assertRaises(AuthorizationError):
            challenges.consume("connection-placeholder", challenge)

        sessions = SessionStore(monotonic=clock)
        session = sessions.create(
            self.phone_identity.credential_id,
            self.rig_identity.credential_id,
            connection_id="connection-placeholder",
        )
        nonce = "bm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm4="
        sessions.consume_nonce(
            session,
            self.phone_identity.credential_id,
            self.rig_identity.credential_id,
            nonce=nonce,
            connection_id="connection-placeholder",
        )
        with self.assertRaises(AuthorizationError):
            sessions.require(
                session,
                self.phone_identity.credential_id,
                self.rig_identity.credential_id,
                connection_id="connection-placeholder",
                nonce=nonce,
            )
        self.assertFalse(continuity_is_stale(clock.value - 60, None, now=clock.value))
        self.assertTrue(continuity_is_stale(clock.value - 24 * 60 * 60, None, now=clock.value))
        self.assertTrue(continuity_is_stale(clock.value + 3600, None, now=clock.value))

    def test_partitioned_transport_budgets_preserve_rig_wide_bounds(self):
        self.assertEqual(BLE_AUTH_ATTEMPT_CAPACITY + HTTP_AUTH_ATTEMPT_CAPACITY, 12)
        self.assertEqual(
            (1.0 / BLE_AUTH_ATTEMPT_REFILL_SECONDS) +
            (1.0 / HTTP_AUTH_ATTEMPT_REFILL_SECONDS),
            1.0 / 5,
        )
        self.assertEqual(BLE_UNKNOWN_CREDENTIAL_LIMIT + HTTP_UNKNOWN_CREDENTIAL_LIMIT, 10)
        self.assertEqual(
            BLE_CREDENTIAL_ATTEMPT_CAPACITY + HTTP_CREDENTIAL_ATTEMPT_CAPACITY,
            3,
        )
        self.assertEqual(
            (1.0 / BLE_CREDENTIAL_REFILL_SECONDS) +
            (1.0 / HTTP_CREDENTIAL_REFILL_SECONDS),
            1.0 / 30,
        )
        self.assertEqual(
            BLE_MAX_SESSIONS_PER_CREDENTIAL + HTTP_MAX_SESSIONS_PER_CREDENTIAL,
            2,
        )
        self.assertEqual(BLE_MAX_SESSIONS_GLOBAL + HTTP_MAX_SESSIONS_GLOBAL, 8)

        sessions = SessionStore(
            maximum_per_credential=BLE_MAX_SESSIONS_PER_CREDENTIAL,
            maximum_global=BLE_MAX_SESSIONS_GLOBAL,
        )
        first = sessions.create(
            self.phone_identity.credential_id,
            self.rig_identity.credential_id,
        )
        second = sessions.create(
            self.phone_identity.credential_id,
            self.rig_identity.credential_id,
        )
        with self.assertRaises(AuthorizationError):
            sessions.require(
                first,
                self.phone_identity.credential_id,
                self.rig_identity.credential_id,
            )
        sessions.require(
            second,
            self.phone_identity.credential_id,
            self.rig_identity.credential_id,
        )

    def test_replay_store_is_shared_durable_bounded_and_ack_digest_aware(self):
        replay_path = os.path.join(self.tmp, "authorization-replay.sqlite3")
        authority = realm_id_for_nightscout("https://diyps.example.invalid")
        credential_id = self.phone_identity.credential_id
        first = AuthorizationReplayStore(
            replay_path,
            maximum_per_kind=3,
            maximum_total=5,
        )
        second = AuthorizationReplayStore(
            replay_path,
            maximum_per_kind=3,
            maximum_total=5,
        )
        try:
            first.consume(
                "hello",
                authority,
                credential_id,
                "11111111-1111-4111-8111-111111111111",
            )
            with self.assertRaises(AuthorizationReplayError):
                second.consume(
                    "hello",
                    authority,
                    credential_id,
                    "11111111-1111-4111-8111-111111111111",
                )

            first.consume("event", authority, credential_id, "event-placeholder", "a" * 64)
            with self.assertRaises(AuthorizationReplayError):
                second.consume("event", authority, credential_id, "event-placeholder", "a" * 64)
            self.assertTrue(second.consume(
                "event",
                authority,
                credential_id,
                "event-placeholder",
                "b" * 64,
            ))

            runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
            runtime.client = type("ReplayClient", (object,), {
                "authority_context_id": authority,
            })()
            runtime.replay = second
            self.assertTrue(runtime.consume_replay(
                "event",
                credential_id,
                "runtime-event-placeholder",
                ack_digest="c" * 64,
            ))
            for message_id in (
                "22222222-2222-4222-8222-222222222222",
                "33333333-3333-4333-8333-333333333333",
                "44444444-4444-4444-8444-444444444444",
            ):
                first.consume("hello", authority, credential_id, message_id)
            counts = first.counts()
            self.assertLessEqual(counts["hello"], 3)
            self.assertLessEqual(counts["event"], 3)
            self.assertLessEqual(counts["total"], 5)
            self.assertEqual(stat.S_IMODE(os.stat(replay_path).st_mode), 0o600)
        finally:
            first.close()
            second.close()

        reopened = AuthorizationReplayStore(replay_path)
        try:
            with self.assertRaises(AuthorizationReplayError):
                reopened.consume(
                    "event",
                    authority,
                    credential_id,
                    "runtime-event-placeholder",
                    "c" * 64,
                )
        finally:
            reopened.close()

    def test_ble_chunk_assembly_is_connection_scoped_and_clearable(self):
        assembler = BleChunkAssembler()

        def envelope(message_id, seq, total, payload):
            return {
                "message_id": message_id,
                "seq": seq,
                "total": total,
                "payload": payload,
            }

        self.assertIsNone(assembler.add(envelope("shared-message", 0, 2, b"a0"), "connection-a"))
        self.assertIsNone(assembler.add(envelope("shared-message", 0, 2, b"b0"), "connection-b"))
        self.assertEqual(
            assembler.add(envelope("shared-message", 1, 2, b"a1"), "connection-a"),
            b"a0a1",
        )
        self.assertEqual(
            assembler.add(envelope("shared-message", 1, 2, b"b1"), "connection-b"),
            b"b0b1",
        )

        self.assertIsNone(assembler.add(envelope("partial", 0, 2, b"a0"), "connection-a"))
        self.assertIsNone(assembler.add(envelope("partial", 0, 2, b"b0"), "connection-b"))
        assembler.clear_connection("connection-a")
        self.assertIsNone(assembler.add(envelope("partial", 1, 2, b"a1"), "connection-a"))
        self.assertEqual(
            assembler.add(envelope("partial", 1, 2, b"b1"), "connection-b"),
            b"b0b1",
        )

    def test_ble_auth_hello_limits_apply_before_assembly_completes(self):
        assembler = BleChunkAssembler()
        auth_prefix = b'{"schema":"openaps.ble.auth-hello.v1",'
        escaped_auth_prefix = b'{"sch\\u0065ma":"openaps.ble.auth-hell\\u006f.v1",'

        with self.assertRaises(BleProtocolError):
            assembler.add({
                "message_id": "over-chunked-auth",
                "seq": 0,
                "total": MAX_AUTH_CHUNKS + 1,
                "payload": escaped_auth_prefix,
            }, "connection-placeholder")

        first_chunk = auth_prefix + (b" " * (1024 - len(auth_prefix)))
        chunks = [first_chunk] + [b"x" * 1024] * 4
        for index, chunk in enumerate(chunks[:4]):
            self.assertIsNone(assembler.add({
                "message_id": "oversized-auth",
                "seq": index,
                "total": 6,
                "payload": chunk,
            }, "connection-placeholder"))
        with self.assertRaises(BleProtocolError):
            assembler.add({
                "message_id": "oversized-auth",
                "seq": 4,
                "total": 6,
                "payload": chunks[4],
            }, "connection-placeholder")

        self.assertEqual(
            assembler.add({
                "message_id": "oversized-auth",
                "seq": 0,
                "total": 1,
                "payload": b"{}",
            }, "connection-placeholder"),
            b"{}",
        )

    def test_rig_info_reconnect_clears_connection_assembly_session_and_challenge(self):
        rig = self.rig_identity

        class Client(object):
            @staticmethod
            def carrier_ready():
                return True

        class Runtime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = Client()
            carrier_ready_cached = True
            last_state = {"classification": "present"}

            @staticmethod
            def start_periodic_reconciliation():
                return None

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        connection_a = "connection-a"
        connection_b = "connection-b"
        challenge_a = bridge.rig_info_payload(connection_a)["authorization_challenge"]
        challenge_b = bridge.rig_info_payload(connection_b)["authorization_challenge"]
        session_a = bridge.authorization_sessions.create(
            self.phone_identity.credential_id,
            rig.credential_id,
            connection_id=connection_a,
        )
        session_b = bridge.authorization_sessions.create(
            self.phone_identity.credential_id,
            rig.credential_id,
            connection_id=connection_b,
        )
        partial_a = {
            "message_id": "partial-message",
            "seq": 0,
            "total": 2,
            "payload": b"a0",
        }
        partial_b = dict(partial_a)
        partial_b["payload"] = b"b0"
        bridge.assembler.add(partial_a, connection_a)
        bridge.assembler.add(partial_b, connection_b)

        replacement_challenge = bridge.rig_info_payload(connection_a)["authorization_challenge"]

        with self.assertRaises(AuthorizationError):
            bridge.authorization_challenges.validate(connection_a, challenge_a)
        bridge.authorization_challenges.validate(connection_a, replacement_challenge)
        bridge.authorization_challenges.validate(connection_b, challenge_b)
        with self.assertRaises(AuthorizationError):
            bridge.authorization_sessions.require(
                session_a,
                self.phone_identity.credential_id,
                rig.credential_id,
                connection_id=connection_a,
            )
        bridge.authorization_sessions.require(
            session_b,
            self.phone_identity.credential_id,
            rig.credential_id,
            connection_id=connection_b,
        )
        self.assertIsNone(bridge.assembler.add({
            "message_id": "partial-message",
            "seq": 1,
            "total": 2,
            "payload": b"a1",
        }, connection_a))
        self.assertEqual(bridge.assembler.add({
            "message_id": "partial-message",
            "seq": 1,
            "total": 2,
            "payload": b"b1",
        }, connection_b), b"b0b1")

        bridge.clear_connection_state(connection_b)
        with self.assertRaises(AuthorizationError):
            bridge.authorization_challenges.validate(connection_b, challenge_b)
        with self.assertRaises(AuthorizationError):
            bridge.authorization_sessions.require(
                session_b,
                self.phone_identity.credential_id,
                rig.credential_id,
                connection_id=connection_b,
            )

    def test_rig_info_advertises_nonmutating_shadow_capability_only_with_receiver(self):
        rig = self.rig_identity

        class ReadyClient(object):
            @staticmethod
            def carrier_ready():
                raise AssertionError("rig info must not read the shared trust store")

        class UnreadyClient(object):
            @staticmethod
            def carrier_ready():
                return False

        class AvailableRuntime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = ReadyClient()
            carrier_ready_cached = True
            last_state = {"classification": "present"}

            @staticmethod
            def start_periodic_reconciliation():
                return None

        class UnavailableRuntime(object):
            mode = "shadow"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "identity_error"}

        class CarrierUnavailableRuntime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = UnreadyClient()
            carrier_ready_cached = False
            last_state = {"classification": "present"}

            @staticmethod
            def start_periodic_reconciliation():
                return None

        config = {
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }
        available = RigBridge(config, authorization_runtime=AvailableRuntime())
        unavailable = RigBridge(config, authorization_runtime=UnavailableRuntime())
        carrier_unavailable = RigBridge(
            config,
            authorization_runtime=CarrierUnavailableRuntime(),
        )

        available_capabilities = available.rig_info_payload("connection-available")["capabilities"]
        unavailable_info = unavailable.rig_info_payload("connection-unavailable")
        carrier_unavailable_info = carrier_unavailable.rig_info_payload(
            "connection-carrier-unavailable"
        )
        self.assertIn("authorization_shadow_nonmutating_v1", available_capabilities)
        self.assertNotIn(
            "authorization_shadow_nonmutating_v1",
            unavailable_info["capabilities"],
        )
        self.assertNotIn(
            "authorization_shadow_nonmutating_v1",
            carrier_unavailable_info["capabilities"],
        )
        self.assertNotIn("signed_event_v2", carrier_unavailable_info["capabilities"])
        self.assertNotIn("authorization_challenge", carrier_unavailable_info)
        self.assertEqual(
            carrier_unavailable_info["authorization_mode"],
            "shadow_unavailable",
        )

    def test_ble_auth_admission_precedes_carrier_refresh_trigger(self):
        phone = self.phone_identity
        rig = self.rig_identity

        class Trust(object):
            @staticmethod
            def peer(_credential_id):
                return None

        class Client(object):
            trust = Trust()

        class Runtime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = Client()
            carrier_ready_cached = True
            last_state = {"classification": "present"}

            def __init__(self):
                self.carrier_checks = 0

            @staticmethod
            def start_periodic_reconciliation():
                return None

            def ensure_shadow_carrier_ready(self):
                self.carrier_checks += 1
                return False

        runtime = Runtime()
        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=runtime)
        connection_id = "connection-admission-placeholder"

        with self.assertRaises(AuthorizationError):
            bridge._submit_auth_hello({}, connection_id, 2, 1)
        self.assertEqual(runtime.carrier_checks, 0)

        info = bridge.rig_info_payload(connection_id)
        hello = build_auth_hello(
            phone,
            rig.credential_id,
            info["authorization_challenge"],
            phone_challenge=b"p" * 32,
        )
        encoded = json.dumps(hello, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with self.assertRaises(AuthorizationError):
            bridge._submit_auth_hello(hello, connection_id, len(encoded), 1)
        self.assertEqual(runtime.carrier_checks, 1)
        self.assertIn(phone.credential_id, bridge.authorization_credential_attempts)

    def test_rig_info_uses_cached_carrier_state_without_waiting_for_store_lock(self):
        rig = self.rig_identity
        authority_context_id = realm_id_for_nightscout(
            "https://diyps.example.invalid"
        )
        trust = ShadowTrustStore(
            os.path.join(self.tmp, "locked-shadow-state.json"),
            authority_context_id=authority_context_id,
            local_credential_id=rig.credential_id,
            local_device_kind="rig",
            identity=rig,
        )

        class Client(object):
            def __init__(self):
                self.trust = trust

            def carrier_ready(self):
                self.trust.self_state()
                return True

        class Runtime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = Client()
            carrier_ready_cached = False
            last_state = {"classification": "present"}

            @staticmethod
            def start_periodic_reconciliation():
                return None

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        completed = threading.Event()
        outcome = {}
        with open(trust.lock_path, "a+") as held_lock:
            fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX)

            def read_rig_info():
                outcome["info"] = bridge.rig_info_payload("connection-locked-store")
                completed.set()

            reader = threading.Thread(target=read_rig_info)
            reader.start()
            try:
                self.assertTrue(completed.wait(0.25))
            finally:
                fcntl.flock(held_lock.fileno(), fcntl.LOCK_UN)
                reader.join(1)
        info = outcome["info"]
        self.assertEqual(info["authorization_mode"], "shadow_unavailable")
        self.assertNotIn("authorization_challenge", info)
        self.assertNotIn("signed_event_v2", info["capabilities"])

    def test_bluez_disconnect_clears_only_that_connections_authorization_and_ack_state(self):
        rig = self.rig_identity

        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        connection_a = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        connection_b = "/org/bluez/hci0/dev_BB_BB_BB_BB_BB_BB"
        challenge_a = bridge.authorization_challenges.issue(connection_a)
        challenge_b = bridge.authorization_challenges.issue(connection_b)
        session_a = bridge.authorization_sessions.create(
            self.phone_identity.credential_id,
            rig.credential_id,
            connection_id=connection_a,
        )
        session_b = bridge.authorization_sessions.create(
            self.phone_identity.credential_id,
            rig.credential_id,
            connection_id=connection_b,
        )
        bridge.assembler.add({
            "message_id": "shared-partial",
            "seq": 0,
            "total": 2,
            "payload": b"a0",
        }, connection_a)
        bridge.assembler.add({
            "message_id": "shared-partial",
            "seq": 0,
            "total": 2,
            "payload": b"b0",
        }, connection_b)
        ack_a = {"schema": "openaps.ble.event-ack.v2", "event_id": "event-a"}
        ack_b = {"schema": "openaps.local.event_ack.v1", "event_id": "event-b"}
        bridge._publish_ack(ack_a, connection_id=connection_a)
        bridge._publish_ack(ack_b, connection_id=connection_b)
        with Characteristic._read_buffers_lock:
            Characteristic._read_buffers[(connection_a, BLE_ACK_CHAR_UUID)] = (
                [b"old-a-0", b"old-a-1"],
                1,
                time.time(),
            )
            Characteristic._read_buffers[(connection_b, BLE_ACK_CHAR_UUID)] = (
                [b"old-b-0", b"old-b-1"],
                1,
                time.time(),
            )

        self.assertTrue(bridge.handle_device_properties_changed(
            BLUEZ_DEVICE_IFACE,
            {"Connected": False},
            connection_a,
        ))
        self.assertEqual(bridge.ack_for_connection(connection_a)["ack_status"], "idle")
        self.assertEqual(bridge.ack_for_connection(connection_b), ack_b)
        with Characteristic._read_buffers_lock:
            self.assertNotIn((connection_a, BLE_ACK_CHAR_UUID), Characteristic._read_buffers)
            self.assertIn((connection_b, BLE_ACK_CHAR_UUID), Characteristic._read_buffers)
        with self.assertRaises(AuthorizationError):
            bridge.authorization_challenges.validate(connection_a, challenge_a)
        bridge.authorization_challenges.validate(connection_b, challenge_b)
        with self.assertRaises(AuthorizationError):
            bridge.authorization_sessions.require(
                session_a,
                self.phone_identity.credential_id,
                rig.credential_id,
                connection_id=connection_a,
            )
        bridge.authorization_sessions.require(
            session_b,
            self.phone_identity.credential_id,
            rig.credential_id,
            connection_id=connection_b,
        )
        self.assertIsNone(bridge.assembler.add({
            "message_id": "shared-partial",
            "seq": 1,
            "total": 2,
            "payload": b"a1",
        }, connection_a))
        self.assertEqual(bridge.assembler.add({
            "message_id": "shared-partial",
            "seq": 1,
            "total": 2,
            "payload": b"b1",
        }, connection_b), b"b0b1")
        Characteristic.clear_read_buffer(connection_b)

    def test_replacing_connection_ack_discards_cached_chunks_from_prior_ack(self):
        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        connection_id = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        signed_ack = {"schema": "openaps.ble.event-ack.v2", "event_id": "signed"}
        legacy_ack = {"schema": "openaps.local.event_ack.v1", "event_id": "legacy"}
        bridge._publish_ack(signed_ack, connection_id=connection_id)
        with Characteristic._read_buffers_lock:
            Characteristic._read_buffers[(connection_id, BLE_ACK_CHAR_UUID)] = (
                [b"signed-0", b"signed-1"],
                1,
                time.time(),
            )

        bridge._publish_ack(legacy_ack, connection_id=connection_id)

        self.assertEqual(bridge.ack_for_connection(connection_id), legacy_ack)
        with Characteristic._read_buffers_lock:
            self.assertNotIn((connection_id, BLE_ACK_CHAR_UUID), Characteristic._read_buffers)

    def test_connection_bound_authorization_acks_are_not_globally_notified(self):
        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        class AckNotificationHarness(object):
            def __init__(self):
                self.values = []

            def _set_value(self, value):
                self.values.append(value)

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        connection_id = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        notifications = AckNotificationHarness()
        bridge.ack_characteristic = notifications

        legacy_ack = {
            "schema": "openaps.local.event_ack.v1",
            "event_id": "legacy-event",
        }
        auth_ack = {
            "schema": "openaps.ble.auth-ack.v1",
            "session_id": "authorization-session",
        }
        signed_ack = {
            "schema": "openaps.ble.event-ack.v2",
            "event_id": "signed-event",
        }

        bridge._publish_ack(legacy_ack, connection_id=connection_id)
        bridge._publish_ack(auth_ack, connection_id=connection_id)
        bridge._publish_ack(signed_ack, connection_id=connection_id)

        self.assertEqual(notifications.values, [ble_server_module._json_bytes(legacy_ack)])
        self.assertEqual(bridge.ack_for_connection(connection_id), signed_ack)

    def test_authorization_ack_handoff_replaces_a_stale_read_path_buffer_once(self):
        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        clock = FakeClock()
        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime(), monotonic=clock)
        writer_connection = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        reader_connection = "/org/bluez/hci0/dev_BB_BB_BB_BB_BB_BB"
        other_connection = "/org/bluez/hci0/dev_CC_CC_CC_CC_CC_CC"
        auth_ack = {
            "schema": "openaps.ble.auth-ack.v1",
            "session_id": "authorization-session",
        }
        bridge._publish_ack(auth_ack, connection_id=writer_connection)
        with Characteristic._read_buffers_lock:
            Characteristic._read_buffers[(reader_connection, BLE_ACK_CHAR_UUID)] = (
                [b"stale-legacy-0", b"stale-legacy-1"],
                1,
                time.time(),
            )

        class AckReadHarness(object):
            uuid = BLE_ACK_CHAR_UUID

            def __init__(self, target_bridge):
                self.bridge = target_bridge

            def _read_state_lock(self, _options):
                return self.bridge._connection_state_lock

            def _prepare_read(self, options, connection_id):
                return ble_server_module.AckCharacteristic._prepare_read(
                    self,
                    options,
                    connection_id,
                )

            def _read_value(self, options):
                return ble_server_module.AckCharacteristic._read_value(self, options)

        harness = AckReadHarness(bridge)
        original_array_encoder = ble_server_module._bytes_to_dbus_array
        ble_server_module._bytes_to_dbus_array = lambda data: bytes(bytearray(data))
        try:
            first_chunk = Characteristic.ReadValue(
                harness,
                {"device": reader_connection},
            )
        finally:
            ble_server_module._bytes_to_dbus_array = original_array_encoder

        self.assertNotEqual(first_chunk, b"stale-legacy-1")
        self.assertEqual(bridge.ack_for_connection(writer_connection), auth_ack)
        self.assertEqual(bridge.ack_for_connection(reader_connection), auth_ack)
        self.assertEqual(
            bridge.ack_for_connection(other_connection)["ack_status"],
            "idle",
        )
        self.assertFalse(bridge.prepare_authorization_ack_read(other_connection))
        Characteristic.clear_read_buffer(reader_connection)

    def test_authorization_ack_handoff_expires_and_clears_on_writer_disconnect(self):
        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        clock = FakeClock()
        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime(), monotonic=clock)
        writer_connection = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        reader_connection = "/org/bluez/hci0/dev_BB_BB_BB_BB_BB_BB"
        auth_ack = {
            "schema": "openaps.ble.auth-ack.v1",
            "session_id": "authorization-session",
        }

        bridge._publish_ack(auth_ack, connection_id=writer_connection)
        clock.advance(15.1)
        self.assertFalse(bridge.prepare_authorization_ack_read(reader_connection))
        self.assertEqual(
            bridge.ack_for_connection(reader_connection)["ack_status"],
            "idle",
        )

        bridge._publish_ack(auth_ack, connection_id=writer_connection)
        bridge.clear_connection_state(writer_connection)
        self.assertFalse(bridge.prepare_authorization_ack_read(reader_connection))

    def test_authorization_ack_handoff_never_replaces_an_active_ack_or_a_signed_ack(self):
        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        writer_connection = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        reader_connection = "/org/bluez/hci0/dev_BB_BB_BB_BB_BB_BB"
        auth_ack = {
            "schema": "openaps.ble.auth-ack.v1",
            "session_id": "authorization-session",
        }
        active_legacy_ack = {
            "schema": "openaps.local.event_ack.v1",
            "ack_status": "stored",
            "event_id": "active-event",
        }
        signed_ack = {
            "schema": "openaps.ble.event-ack.v2",
            "event_id": "signed-event",
        }

        bridge._publish_ack(auth_ack, connection_id=writer_connection)
        bridge._publish_ack(active_legacy_ack, connection_id=reader_connection)
        self.assertFalse(bridge.prepare_authorization_ack_read(reader_connection))
        self.assertEqual(
            bridge.ack_for_connection(reader_connection),
            active_legacy_ack,
        )

        bridge.clear_connection_state(reader_connection)
        bridge._publish_ack(signed_ack, connection_id=writer_connection)
        self.assertFalse(bridge.prepare_authorization_ack_read(reader_connection))
        self.assertEqual(
            bridge.ack_for_connection(reader_connection)["ack_status"],
            "idle",
        )

    def test_ack_snapshot_and_chunk_install_are_atomic_with_replacement(self):
        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        connection_id = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        old_ack = {
            "schema": "openaps.ble.event-ack.v2",
            "event_id": "old-signed",
            "padding": "x" * 600,
        }
        new_ack = {"schema": "openaps.local.event_ack.v1", "event_id": "new-legacy"}
        bridge._publish_ack(old_ack, connection_id=connection_id)
        snapshot_taken = threading.Event()
        release_snapshot = threading.Event()
        read_done = threading.Event()
        publish_done = threading.Event()
        original_array_encoder = ble_server_module._bytes_to_dbus_array

        class AckReadHarness(object):
            uuid = BLE_ACK_CHAR_UUID

            @staticmethod
            def _read_state_lock(_options):
                return bridge._connection_state_lock

        ack_characteristic = AckReadHarness()

        def delayed_read(options):
            data = ble_server_module._json_bytes(
                bridge.ack_for_connection(str(options.get("device", "")))
            )
            snapshot_taken.set()
            if not release_snapshot.wait(3):
                raise RuntimeError("test ACK snapshot release timed out")
            return data

        ack_characteristic._read_value = delayed_read
        ble_server_module._bytes_to_dbus_array = lambda data: bytes(bytearray(data))

        def read_old_ack():
            try:
                Characteristic.ReadValue(
                    ack_characteristic,
                    {"device": connection_id},
                )
            finally:
                read_done.set()

        def replace_ack():
            bridge._publish_ack(new_ack, connection_id=connection_id)
            publish_done.set()

        reader = threading.Thread(target=read_old_ack)
        publisher = threading.Thread(target=replace_ack)
        try:
            reader.start()
            self.assertTrue(snapshot_taken.wait(1))
            publisher.start()
            self.assertFalse(publish_done.wait(0.1))
            release_snapshot.set()
            self.assertTrue(read_done.wait(1))
            self.assertTrue(publish_done.wait(1))
        finally:
            release_snapshot.set()
            reader.join(1)
            publisher.join(1)
            ble_server_module._bytes_to_dbus_array = original_array_encoder
        self.assertEqual(bridge.ack_for_connection(connection_id), new_ack)
        with Characteristic._read_buffers_lock:
            self.assertNotIn((connection_id, BLE_ACK_CHAR_UUID), Characteristic._read_buffers)

    def test_slow_ble_shadow_work_does_not_block_legacy_or_cross_connection_acks(self):
        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        shadow_started = threading.Event()
        release_shadow = threading.Event()
        shadow_done = threading.Event()
        legacy_done = threading.Event()
        shadow_errors = []
        legacy_errors = []
        shadow_ack = {"schema": "openaps.ble.auth-ack.v1", "message_id": "auth-message"}
        legacy_ack = {"schema": "openaps.local.event_ack.v1", "event_id": "legacy-event"}

        def slow_auth(*_args):
            shadow_started.set()
            if not release_shadow.wait(3):
                raise RuntimeError("test shadow release timed out")
            return shadow_ack

        bridge._submit_auth_hello = slow_auth
        bridge.post_event = lambda _event: legacy_ack
        auth_message = json.dumps({
            "schema": AUTH_HELLO_SCHEMA,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        auth_envelope = json.dumps({
            "envelope_version": 1,
            "message_id": "auth-message",
            "seq": 0,
            "total": 1,
            "encoding": "base64",
            "payload": base64.b64encode(auth_message).decode("ascii"),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        legacy_event = json.dumps({
            "schema": "openaps.local.event.v1",
            "event_id": "legacy-event",
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")

        started_at = time.monotonic()
        bridge.submit_ble_write_async(
            auth_envelope,
            connection_id="connection-shadow",
            on_success=lambda _ack: shadow_done.set(),
            on_error=lambda exc: (shadow_errors.append(exc), shadow_done.set()),
        )
        self.assertLess(time.monotonic() - started_at, 0.5)
        self.assertTrue(shadow_started.wait(1))
        try:
            bridge.submit_ble_write_async(
                legacy_event,
                connection_id="connection-legacy",
                on_success=lambda _ack: legacy_done.set(),
                on_error=lambda exc: (legacy_errors.append(exc), legacy_done.set()),
            )
            self.assertTrue(legacy_done.wait(1))
            self.assertFalse(legacy_errors)
            self.assertEqual(bridge.ack_for_connection("connection-legacy"), legacy_ack)
            self.assertEqual(
                bridge.ack_for_connection("connection-shadow")["ack_status"],
                "idle",
            )
        finally:
            release_shadow.set()
        self.assertTrue(shadow_done.wait(1))
        self.assertFalse(shadow_errors)
        self.assertEqual(bridge.ack_for_connection("connection-shadow"), shadow_ack)
        self.assertEqual(bridge.ack_for_connection("connection-legacy"), legacy_ack)

    def test_disconnect_during_auth_worker_invalidates_late_created_session(self):
        rig = self.rig_identity
        phone = self.phone_identity

        class Runtime(object):
            mode = "legacy"
            identity = None
            credential_id = None
            client = None
            last_state = {"classification": "legacy"}

        bridge = RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
        }, authorization_runtime=Runtime())
        connection_id = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"
        worker_started = threading.Event()
        release_worker = threading.Event()
        worker_done = threading.Event()
        outcome = {}

        def auth_that_creates_session_after_disconnect(*_args):
            worker_started.set()
            if not release_worker.wait(3):
                raise RuntimeError("test worker release timed out")
            outcome["session_id"] = bridge.authorization_sessions.create(
                phone.credential_id,
                rig.credential_id,
                connection_id=connection_id,
            )
            return {"schema": "openaps.ble.auth-ack.v1", "message_id": "late-auth"}

        bridge._submit_auth_hello = auth_that_creates_session_after_disconnect
        auth_message = json.dumps({"schema": AUTH_HELLO_SCHEMA}).encode("utf-8")
        auth_envelope = json.dumps({
            "envelope_version": 1,
            "message_id": "late-auth",
            "seq": 0,
            "total": 1,
            "encoding": "base64",
            "payload": base64.b64encode(auth_message).decode("ascii"),
        }).encode("utf-8")
        bridge.submit_ble_write_async(
            auth_envelope,
            connection_id=connection_id,
            on_success=lambda _ack: (outcome.update({"success": True}), worker_done.set()),
            on_error=lambda exc: (outcome.update({"error": exc}), worker_done.set()),
        )
        self.assertTrue(worker_started.wait(1))
        bridge.handle_device_properties_changed(
            BLUEZ_DEVICE_IFACE,
            {"Connected": False},
            connection_id,
        )
        release_worker.set()
        self.assertTrue(worker_done.wait(1))
        self.assertIn("error", outcome)
        self.assertNotIn("success", outcome)
        with self.assertRaises(AuthorizationError):
            bridge.authorization_sessions.require(
                outcome["session_id"],
                phone.credential_id,
                rig.credential_id,
                connection_id=connection_id,
            )
        self.assertEqual(bridge.ack_for_connection(connection_id)["ack_status"], "idle")

    def test_jwt_uses_duration_and_monotonic_clock_with_one_401_retry(self):
        clock = FakeClock(5000)
        transport = AuthorizationTransport()
        provider = TemporaryJWTProvider(transport, "access-placeholder", monotonic=clock)
        token = provider.get()
        self.assertEqual(token.count("."), 2)
        self.assertEqual(provider.subject, "subject-placeholder")
        first_deadline = provider.renew_at
        clock.advance(60)
        self.assertEqual(provider.get(), token)
        self.assertEqual(transport.exchange_count, 1)
        self.assertGreater(first_deadline, clock.value)

        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "state.json"),
            transport=transport,
            monotonic=clock,
            wallclock=lambda: -2208988800,
        )
        transport.force_one_401 = True
        self.assertEqual(client.status()["srvDate"], 1893553445000)
        self.assertEqual(transport.exchange_count, 3)

        fallback_transport = AuthorizationTransport(compact_lifetime_only=True)
        fallback_provider = TemporaryJWTProvider(
            fallback_transport,
            "token=access-placeholder",
            monotonic=FakeClock(7000),
        )
        self.assertEqual(fallback_provider.get().count("."), 2)
        self.assertEqual(fallback_provider.access_token, "access-placeholder")
        self.assertEqual(fallback_provider.subject, "subject-placeholder")

    def test_jwt_accepts_pinned_top_level_envelope_and_strips_token_prefix(self):
        class PinnedEnvelopeTransport(object):
            def __init__(self):
                self.requests = []

            def request(self, method, path, body=None, bearer=None, query=None):
                self.requests.append((method, path, body, bearer, query))
                return 200, {
                    "token": compact_jwt("access-placeholder", None, None),
                    "sub": "subject-placeholder",
                    "permissionGroups": [["api:devicestatus:read"]],
                    "iat": 10,
                    "exp": 10 + 8 * 60 * 60,
                }

        transport = PinnedEnvelopeTransport()
        provider = TemporaryJWTProvider(
            transport,
            "token=access-placeholder",
            monotonic=FakeClock(9000),
        )
        token = provider.get()

        self.assertEqual(token.count("."), 2)
        self.assertEqual(provider.access_token, "access-placeholder")
        self.assertEqual(provider.subject, "subject-placeholder")
        self.assertEqual(
            transport.requests[0][1],
            "/api/v2/authorization/request/access-placeholder",
        )

    def test_jwt_access_token_claim_must_match_normalized_configured_token(self):
        class MismatchedTokenTransport(object):
            @staticmethod
            def request(method, path, body=None, bearer=None, query=None):
                return 200, {
                    "token": compact_jwt("different-access-token", 10, 3610),
                    "sub": "subject-placeholder",
                    "iat": 10,
                    "exp": 3610,
                }

        provider = TemporaryJWTProvider(
            MismatchedTokenTransport(),
            "token=expected-access-token",
            monotonic=FakeClock(9100),
        )
        with self.assertRaises(NightscoutAuthorizationError) as raised:
            provider.get()
        self.assertEqual(raised.exception.category, "invalid_jwt_exchange")

    def test_jwt_late_initial_401_reuses_newer_generation(self):
        class LateInitial401Transport(object):
            def __init__(self):
                self.lock = threading.Lock()
                self.exchange_count = 0
                self.tokens = []
                self.first_t1_entered = threading.Event()
                self.release_first_t1 = threading.Event()
                self.t1_status_calls = 0

            def request(self, method, path, body=None, bearer=None, query=None):
                if path.startswith("/api/v2/authorization/request/"):
                    with self.lock:
                        self.exchange_count += 1
                        token = compact_jwt(
                            "access-placeholder",
                            10,
                            10 + 8 * 60 * 60,
                            str(self.exchange_count),
                        )
                        self.tokens.append(token)
                    return 200, {
                        "token": token,
                        "sub": "subject-placeholder",
                        "iat": 10,
                        "exp": 10 + 8 * 60 * 60,
                    }
                if path == "/api/v3/status":
                    with self.lock:
                        is_first_token = bool(self.tokens and bearer == self.tokens[0])
                        if is_first_token:
                            self.t1_status_calls += 1
                            call = self.t1_status_calls
                        else:
                            call = None
                    if is_first_token and call == 1:
                        self.first_t1_entered.set()
                        if not self.release_first_t1.wait(5):
                            raise RuntimeError("late 401 release timed out")
                        return 401, {"status": 401}
                    if is_first_token:
                        return 401, {"status": 401}
                    return 200, {"status": 200, "result": {"srvDate": 1}}
                raise AssertionError("unexpected request")

        transport = LateInitial401Transport()
        client = NightscoutDeviceAuthorizationClient(
            "https://jwt-race.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "jwt-late-initial-state.json"),
            transport=transport,
        )
        first_token = client.jwt.get()
        outcomes = []
        errors = []

        def late_request():
            try:
                outcomes.append(client._authenticated_request("GET", "/api/v3/status")[0])
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=late_request)
        thread.daemon = True
        thread.start()
        self.assertTrue(transport.first_t1_entered.wait(2))
        outcomes.append(client._authenticated_request("GET", "/api/v3/status")[0])
        transport.release_first_t1.set()
        thread.join(5)

        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(sorted(outcomes), [200, 200])
        self.assertEqual(transport.exchange_count, 2)
        self.assertNotEqual(client.jwt.get(), first_token)
        self.assertEqual(transport.exchange_count, 2)
        self.assertEqual(client.jwt.backoff_until, 0.0)

    def test_jwt_late_retry_401_does_not_reject_newer_generation(self):
        class LateRetry401Transport(object):
            def __init__(self):
                self.lock = threading.Lock()
                self.exchange_count = 0
                self.tokens = []
                self.t2_status_calls = 0
                self.first_t2_entered = threading.Event()
                self.release_first_t2 = threading.Event()

            def request(self, method, path, body=None, bearer=None, query=None):
                if path.startswith("/api/v2/authorization/request/"):
                    with self.lock:
                        self.exchange_count += 1
                        token = compact_jwt(
                            "access-placeholder",
                            10,
                            10 + 8 * 60 * 60,
                            str(self.exchange_count),
                        )
                        self.tokens.append(token)
                    return 200, {
                        "token": token,
                        "sub": "subject-placeholder",
                        "iat": 10,
                        "exp": 10 + 8 * 60 * 60,
                    }
                if path == "/api/v3/status":
                    with self.lock:
                        token_index = self.tokens.index(bearer)
                        if token_index == 1:
                            self.t2_status_calls += 1
                            call = self.t2_status_calls
                        else:
                            call = None
                    if token_index == 0:
                        return 401, {"status": 401}
                    if token_index == 1 and call == 1:
                        self.first_t2_entered.set()
                        if not self.release_first_t2.wait(5):
                            raise RuntimeError("late retry release timed out")
                        return 401, {"status": 401}
                    if token_index == 1:
                        return 401, {"status": 401}
                    return 200, {"status": 200, "result": {"srvDate": 1}}
                raise AssertionError("unexpected request")

        transport = LateRetry401Transport()
        client = NightscoutDeviceAuthorizationClient(
            "https://jwt-reject-race.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "jwt-late-retry-state.json"),
            transport=transport,
        )
        client.jwt.get()
        first_outcome = []
        first_errors = []

        def first_request():
            try:
                first_outcome.append(
                    client._authenticated_request("GET", "/api/v3/status")[0]
                )
            except Exception as exc:
                first_errors.append(exc)

        first = threading.Thread(target=first_request)
        first.daemon = True
        first.start()
        self.assertTrue(transport.first_t2_entered.wait(2))
        second_status = client._authenticated_request("GET", "/api/v3/status")[0]
        transport.release_first_t2.set()
        first.join(5)

        self.assertFalse(first.is_alive())
        self.assertFalse(first_errors)
        self.assertEqual(first_outcome, [401])
        self.assertEqual(second_status, 200)
        self.assertEqual(transport.exchange_count, 3)
        self.assertEqual(client.jwt.get(), transport.tokens[2])
        self.assertEqual(client.jwt.backoff_until, 0.0)

    def test_security_probe_and_zero_friction_self_enrollment(self):
        transport = AuthorizationTransport(identity=self.rig_identity)
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "state.json"),
            transport=transport,
        )
        state = client.reconcile_self()
        self.assertEqual(state["classification"], "present")
        self.assertTrue(state["capability"]["security_enabled"])
        self.assertTrue(state["capability"]["read"])
        self.assertTrue(state["capability"]["create"])
        self.assertEqual(state["duplicate_state"], "one_live_non_authoritative")
        self.assertEqual(state["last_registry_srv_created"], 1893553445000)
        self.assertEqual(state["last_registry_srv_modified"], 1893553445000)
        stored = transport.documents[registry_identifier(self.rig_identity.credential_id)]
        self.assertEqual(stored["subject"], transport.subject)
        self.assertNotIn("identifier", [request[2] for request in transport.requests if request[0] == "PUT" and request[2] and request[2].get("app")][0])

        insecure = AuthorizationTransport(security_enabled=False)
        insecure_client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.phone_identity,
            "phone",
            os.path.join(self.tmp, "insecure-state.json"),
            transport=insecure,
        )
        insecure_state = insecure_client.reconcile_self()
        self.assertEqual(insecure_state["classification"], "unsupported")
        self.assertFalse(insecure_state["capability"]["security_enabled"])
        self.assertFalse(insecure.documents)

    def test_legacy_api_secret_enrolls_rig_and_reads_phone_in_shadow(self):
        transport = LegacyAPISecretAuthorizationTransport()
        state_path = os.path.join(self.tmp, "legacy-api-secret-state.json")
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            None,
            self.rig_identity,
            "rig",
            state_path,
            transport=transport,
            api_secret="0" * 40,
        )

        state = client.reconcile_self()
        self.assertEqual(state["classification"], "present")
        self.assertEqual(state["duplicate_state"], "one_live_non_authoritative")
        self.assertEqual(
            state["capability"]["carrier"],
            LEGACY_V1_AUTHENTICATED_CARRIER,
        )
        self.assertTrue(client.carrier_ready())
        rig_record = transport.documents[0]
        self.assertEqual(
            rig_record["openaps_auth_carrier"],
            LEGACY_V1_AUTHENTICATED_CARRIER,
        )
        self.assertNotIn("subject", rig_record)

        phone_record = build_enrollment_record(
            self.phone_identity,
            "phone",
            "https://diyps.example.invalid",
            transport.server_date,
        )
        phone_record.update({
            "identifier": registry_identifier(self.phone_identity.credential_id),
            "subject": "phone-subject-placeholder",
            "srvCreated": transport.server_date,
            "srvModified": transport.server_date,
        })
        transport.documents.append(phone_record)
        lookup = client.lookup_peer(self.phone_identity.credential_id, "phone")
        self.assertEqual(lookup["classification"], "present")
        self.assertEqual(lookup["duplicate_state"], "one_live_non_authoritative")
        self.assertEqual(
            lookup["peer"]["credential_id"],
            self.phone_identity.credential_id,
        )
        self.assertTrue(any(
            method == "POST" and not authenticated
            for method, _path, _body, authenticated, _query in transport.requests
        ))

    def test_legacy_api_secret_accepts_nonmutating_older_v1_probe_500(self):
        transport = LegacyAPISecretAuthorizationTransport(probe_status=500)
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            None,
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "legacy-api-secret-500-state.json"),
            transport=transport,
            api_secret="0" * 40,
        )
        capability = client.capability_probe()
        self.assertTrue(capability["supported"])
        self.assertTrue(capability["create"])
        self.assertEqual(capability["probe_ordering"], "permission_before_legacy_500")
        self.assertFalse(transport.documents)

    def test_legacy_api_secret_rejects_unprotected_v1_write_route(self):
        transport = LegacyAPISecretAuthorizationTransport(
            unauthenticated_probe_status=200,
        )
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            None,
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "legacy-api-secret-unprotected-state.json"),
            transport=transport,
            api_secret="0" * 40,
        )

        state = client.reconcile_self()

        self.assertEqual(state["classification"], "unsupported")
        self.assertFalse(state["capability"]["supported"])
        self.assertFalse(state["capability"]["security_enabled"])
        self.assertFalse(transport.documents)
        self.assertEqual(len(transport.requests), 1)
        self.assertFalse(transport.requests[0][3])

    def test_create_response_is_top_level_and_definitive_http_failures_are_not_read_back(self):
        expected_path = "/api/v3/devicestatus/" + registry_identifier(self.rig_identity.credential_id)
        cases = [
            ("nested_result", "invalid_create_response", None),
            ("definitive_500", "create", 500),
        ]
        for index, (outcome, category, status) in enumerate(cases):
            with self.subTest(outcome=outcome):
                transport = AuthorizationTransport(
                    identity=self.rig_identity,
                    create_outcome=outcome,
                )
                client = NightscoutDeviceAuthorizationClient(
                    "https://diyps.example.invalid",
                    "access-placeholder",
                    self.rig_identity,
                    "rig",
                    os.path.join(self.tmp, "strict-create-%d.json" % index),
                    transport=transport,
                )

                with self.assertRaises(NightscoutAuthorizationError) as raised:
                    client.reconcile_self()

                self.assertEqual(raised.exception.category, category)
                self.assertEqual(raised.exception.status, status)
                persisted_failure = client.trust.self_state()
                self.assertEqual(
                    persisted_failure["classification"],
                    "ambiguous_create",
                )
                self.assertEqual(
                    persisted_failure["last_attempt_error"],
                    category,
                )
                target_gets = [
                    request for request in transport.requests
                    if request[0] == "GET" and request[1] == expected_path
                ]
                self.assertEqual(len(target_gets), 1)

    def test_create_last_modified_requires_a_positive_integral_timestamp(self):
        for index, last_modified in enumerate((0, -1, 1.5, True, float("inf"))):
            with self.subTest(last_modified=last_modified):
                transport = AuthorizationTransport(
                    identity=self.rig_identity,
                    create_last_modified=last_modified,
                )
                client = NightscoutDeviceAuthorizationClient(
                    "https://diyps.example.invalid",
                    "access-placeholder",
                    self.rig_identity,
                    "rig",
                    os.path.join(self.tmp, "invalid-create-timestamp-%d.json" % index),
                    transport=transport,
                )
                with self.assertRaises(NightscoutAuthorizationError) as raised:
                    client.reconcile_self()
                self.assertEqual(raised.exception.category, "invalid_create_response")

        transport = AuthorizationTransport(
            identity=self.rig_identity,
            create_last_modified=1.0,
        )
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "integral-create-timestamp.json"),
            transport=transport,
        )
        self.assertEqual(client.reconcile_self()["classification"], "present")

    def test_ambiguous_create_network_failure_reads_back_without_retrying_put(self):
        transport = AuthorizationTransport(
            identity=self.rig_identity,
            create_outcome="network_after_store",
        )
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "ambiguous-create.json"),
            transport=transport,
        )

        state = client.reconcile_self()

        expected_path = "/api/v3/devicestatus/" + registry_identifier(self.rig_identity.credential_id)
        enrollment_puts = [
            request for request in transport.requests
            if request[0] == "PUT" and request[1] == expected_path
        ]
        target_gets = [
            request for request in transport.requests
            if request[0] == "GET" and request[1] == expected_path
        ]
        self.assertEqual(state["classification"], "present")
        self.assertEqual(len(enrollment_puts), 1)
        self.assertEqual(len(target_gets), 2)

    def test_post_put_readback_network_failure_is_not_read_twice(self):
        state_path = os.path.join(self.tmp, "single-create-readback.json")
        expected_path = "/api/v3/devicestatus/" + registry_identifier(
            self.rig_identity.credential_id
        )

        class ReadbackFailureTransport(AuthorizationTransport):
            def __init__(self, *args, **kwargs):
                AuthorizationTransport.__init__(self, *args, **kwargs)
                self.exact_get_count = 0

            def request(self, method, path, body=None, bearer=None, query=None):
                if method == "GET" and path == expected_path:
                    self.exact_get_count += 1
                    if self.exact_get_count == 2:
                        raise NightscoutAuthorizationError("network")
                return AuthorizationTransport.request(
                    self,
                    method,
                    path,
                    body=body,
                    bearer=bearer,
                    query=query,
                )

        transport = ReadbackFailureTransport(identity=self.rig_identity)
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=transport,
        )

        state = client.reconcile_self()

        self.assertEqual(state["classification"], "ambiguous_create")
        self.assertEqual(transport.exact_get_count, 2)
        self.assertEqual(len([
            request for request in transport.requests
            if request[0] == "PUT" and request[1] == expected_path
        ]), 1)
        self.assertEqual(len([
            request for request in transport.requests
            if request[0] == "GET" and request[1] == "/api/v3/devicestatus"
        ]), 1)
        persisted = client.trust.self_state()
        self.assertEqual(persisted["classification"], "ambiguous_create")
        self.assertEqual(
            persisted["ambiguous_create_srv_date"],
            transport.server_date,
        )

    def test_ambiguous_create_without_readback_is_persisted_and_server_time_gated(self):
        state_path = os.path.join(self.tmp, "ambiguous-create-held.json")
        wallclock = FakeClock(10000)
        initial_server_date = 1893553445000
        first_transport = AuthorizationTransport(
            identity=self.rig_identity,
            create_outcome="network_without_store",
            server_date=initial_server_date,
        )
        first = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=first_transport,
            wallclock=wallclock,
        )

        first_state = first.reconcile_self()

        expected_path = "/api/v3/devicestatus/" + registry_identifier(
            self.rig_identity.credential_id
        )
        self.assertEqual(first_state["classification"], "ambiguous_create")
        self.assertEqual(
            first_state["ambiguous_create_srv_date"],
            initial_server_date,
        )
        self.assertEqual(first_state["duplicate_state"], "zero_live_non_authoritative")
        self.assertEqual(len([
            request for request in first_transport.requests
            if request[0] == "PUT" and request[1] == expected_path
        ]), 1)
        self.assertEqual(len([
            request for request in first_transport.requests
            if request[0] == "GET" and request[1] == "/api/v3/devicestatus"
        ]), 1)

        restarted_transport = AuthorizationTransport(
            identity=self.rig_identity,
            server_date=initial_server_date + 60 * 60 * 1000,
        )
        restarted = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=restarted_transport,
            wallclock=wallclock,
        )
        cached = restarted.reconcile_self_if_due(6 * 60 * 60, 5 * 60)
        self.assertEqual(cached["classification"], "ambiguous_create")
        self.assertFalse(restarted_transport.requests)

        wallclock.advance(6 * 60 * 60 + 1)
        held = restarted.reconcile_self_if_due(6 * 60 * 60, 5 * 60)
        self.assertEqual(held["classification"], "ambiguous_create")
        self.assertFalse([
            request for request in restarted_transport.requests
            if request[0] == "PUT" and request[1] == expected_path
        ])
        self.assertEqual(len([
            request for request in restarted_transport.requests
            if request[0] == "GET" and request[1] == "/api/v3/devicestatus"
        ]), 1)

        restarted_transport.server_date = (
            initial_server_date + 6 * 60 * 60 * 1000
        )
        present = restarted.reconcile_self()
        self.assertEqual(present["classification"], "present")
        self.assertEqual(len([
            request for request in restarted_transport.requests
            if request[0] == "PUT" and request[1] == expected_path
        ]), 1)

    def test_create_intent_is_durable_before_put_and_put_requires_persistence(self):
        state_path = os.path.join(self.tmp, "create-intent-before-put.json")
        observed_intents = []

        class InspectingTransport(AuthorizationTransport):
            def request(self, method, path, body=None, bearer=None, query=None):
                if (
                    method == "PUT" and
                    isinstance(body, dict) and
                    body.get("app") == "openaps-device-authorization"
                ):
                    with open(state_path, "r") as handle:
                        persisted = json.load(handle)
                    observed_intents.extend(persisted["self"].values())
                return AuthorizationTransport.request(
                    self,
                    method,
                    path,
                    body=body,
                    bearer=bearer,
                    query=query,
                )

        transport = InspectingTransport(
            identity=self.rig_identity,
            create_outcome="network_without_store",
        )
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=transport,
        )
        state = client.reconcile_self()
        self.assertEqual(state["classification"], "ambiguous_create")
        self.assertEqual(len(observed_intents), 1)
        self.assertEqual(observed_intents[0]["classification"], "ambiguous_create")
        self.assertEqual(
            observed_intents[0]["ambiguous_create_srv_date"],
            transport.server_date,
        )

        unsupported_transport = AuthorizationTransport(
            identity=self.rig_identity,
            create_allowed=False,
        )
        unsupported_client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=unsupported_transport,
        )
        retained = unsupported_client.reconcile_self()
        self.assertEqual(retained["classification"], "ambiguous_create")
        self.assertEqual(
            retained["ambiguous_create_srv_date"],
            transport.server_date,
        )

        blocked_path = os.path.join(self.tmp, "create-intent-blocked.json")
        malformed = b'{"schema":"openaps.auth-shadow-state.v2","self":'
        with open(blocked_path, "wb") as handle:
            handle.write(malformed)
        blocked_transport = AuthorizationTransport(identity=self.rig_identity)
        blocked_client = NightscoutDeviceAuthorizationClient(
            "https://blocked-persistence.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            blocked_path,
            transport=blocked_transport,
        )
        with self.assertRaises(NightscoutAuthorizationError) as raised:
            blocked_client.reconcile_self()
        self.assertEqual(raised.exception.category, "trust_state_unavailable")
        expected_path = "/api/v3/devicestatus/" + registry_identifier(
            self.rig_identity.credential_id
        )
        self.assertFalse([
            request for request in blocked_transport.requests
            if request[0] == "PUT" and request[1] == expected_path
        ])
        with open(blocked_path, "rb") as handle:
            self.assertEqual(handle.read(), malformed)

    def test_create_false_never_becomes_carrier_ready(self):
        transport = AuthorizationTransport(
            identity=self.rig_identity,
            create_allowed=False,
        )
        client = NightscoutDeviceAuthorizationClient(
            "https://diyps.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "read-only-state.json"),
            transport=transport,
        )

        state = client.reconcile_self()
        self.assertEqual(state["classification"], "unsupported")
        self.assertTrue(state["capability"]["supported"])
        self.assertTrue(state["capability"]["read"])
        self.assertFalse(state["capability"]["create"])
        self.assertFalse(client.carrier_ready())

        client.trust.record_self({
            "classification": "present",
            "authority_context_id": client.authority_context_id,
            "last_registry_srv_created": 1,
            "last_registry_srv_modified": 1,
            "capability": {
                "supported": True,
                "security_enabled": True,
                "read": True,
                "create": False,
            },
        })
        self.assertFalse(client.carrier_ready())

    def test_shared_self_reconcile_cadence_deduplicates_daemons_and_failures(self):
        clock = FakeClock(10000)
        state_path = os.path.join(self.tmp, "shared-reconcile-state.json")
        first_transport = AuthorizationTransport(identity=self.rig_identity)
        second_transport = AuthorizationTransport(identity=self.rig_identity)
        first = NightscoutDeviceAuthorizationClient(
            "https://shared-reconcile.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=first_transport,
            wallclock=clock,
        )
        second = NightscoutDeviceAuthorizationClient(
            "https://shared-reconcile.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=second_transport,
            wallclock=clock,
        )

        self.assertEqual(
            first.reconcile_self_if_due(6 * 60 * 60, 5 * 60)["classification"],
            "present",
        )
        self.assertEqual(
            second.reconcile_self_if_due(6 * 60 * 60, 5 * 60)["classification"],
            "present",
        )
        self.assertFalse(second_transport.requests)
        clock.advance(6 * 60 * 60 + 1)
        second.reconcile_self_if_due(6 * 60 * 60, 5 * 60)
        self.assertTrue(second_transport.requests)

        class FailingTransport(object):
            def __init__(self):
                self.calls = 0

            def request(self, *_args, **_kwargs):
                self.calls += 1
                raise NightscoutAuthorizationError("network")

        failure_path = os.path.join(self.tmp, "shared-reconcile-failure.json")
        failing_transport = FailingTransport()
        suppressed_transport = FailingTransport()
        failing = NightscoutDeviceAuthorizationClient(
            "https://shared-failure.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            failure_path,
            transport=failing_transport,
            wallclock=clock,
        )
        suppressed = NightscoutDeviceAuthorizationClient(
            "https://shared-failure.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            failure_path,
            transport=suppressed_transport,
            wallclock=clock,
        )
        with self.assertRaises(NightscoutAuthorizationError):
            failing.reconcile_self_if_due(6 * 60 * 60, 5 * 60)
        cached_failure = suppressed.reconcile_self_if_due(6 * 60 * 60, 5 * 60)
        self.assertEqual(cached_failure["classification"], "error")
        self.assertEqual(cached_failure["last_attempt_error"], "network")
        self.assertEqual(failing_transport.calls, 1)
        self.assertEqual(suppressed_transport.calls, 0)

    def test_malformed_trust_store_is_preserved_and_blocks_replacement(self):
        state_path = os.path.join(self.tmp, "malformed-trust-state.json")
        malformed = b'{"schema":"openaps.auth-shadow-state.v2","peers":'
        with open(state_path, "wb") as handle:
            handle.write(malformed)

        authority = realm_id_for_nightscout("https://malformed.example.invalid")
        store = ShadowTrustStore(
            state_path,
            authority_context_id=authority,
            local_credential_id=self.rig_identity.credential_id,
            local_device_kind="rig",
            identity=self.rig_identity,
        )
        with open(state_path, "rb") as handle:
            self.assertEqual(handle.read(), malformed)
        store.record_self({
            "classification": "present",
            "authority_context_id": authority,
            "credential_id": self.rig_identity.credential_id,
            "last_registry_srv_created": 1,
            "last_registry_srv_modified": 1,
            "capability": {
                "supported": True,
                "security_enabled": True,
                "read": True,
                "create": True,
            },
        })
        with open(state_path, "rb") as handle:
            self.assertEqual(handle.read(), malformed)

        prefix = os.path.basename(state_path) + ".malformed-"
        quarantine_paths = [
            os.path.join(self.tmp, name)
            for name in os.listdir(self.tmp)
            if name.startswith(prefix)
        ]
        self.assertEqual(len(quarantine_paths), 1)
        with open(quarantine_paths[0], "rb") as handle:
            self.assertEqual(handle.read(), malformed)
        self.assertEqual(stat.S_IMODE(os.stat(quarantine_paths[0]).st_mode), 0o600)

    def test_malformed_trust_quarantine_write_failure_is_contained(self):
        state_path = os.path.join(self.tmp, "malformed-quarantine-write-state.json")
        malformed = b'{"schema":"openaps.auth-shadow-state.v2","peers":'
        with open(state_path, "wb") as handle:
            handle.write(malformed)
        authority = realm_id_for_nightscout(
            "https://malformed-write.example.invalid"
        )
        original_write = nightscout_authorization_module.os.write

        def failed_write(_descriptor, _value):
            raise OSError("simulated quarantine write failure")

        nightscout_authorization_module.os.write = failed_write
        try:
            store = ShadowTrustStore(
                state_path,
                authority_context_id=authority,
                local_credential_id=self.rig_identity.credential_id,
                local_device_kind="rig",
                identity=self.rig_identity,
            )
        finally:
            nightscout_authorization_module.os.write = original_write

        self.assertTrue(store._persistence_blocked)
        with open(state_path, "rb") as handle:
            self.assertEqual(handle.read(), malformed)

    def test_cached_authority_context_is_not_reused_for_another_nightscout(self):
        state_path = os.path.join(self.tmp, "authority-context-state.json")
        first_client = NightscoutDeviceAuthorizationClient(
            "https://first.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=AuthorizationTransport(identity=self.rig_identity),
        )
        peer = {
            "credential_id": self.phone_identity.credential_id,
            "device_kind": "phone",
            "realm_id": realm_id_for_nightscout("https://first.example.invalid"),
            "registry_identifier": registry_identifier(self.phone_identity.credential_id),
            "public_key_der": self.phone_identity.public_key_der,
            "nightscout_subject": "subject-placeholder",
            "srv_created": 1,
            "srv_modified": 1,
        }
        first_client.trust.record_peer_confirmation(
            peer,
            "one_live_non_authoritative",
            authority_context_id=first_client.authority_context_id,
        )
        first_client.trust.record_self({
            "classification": "present",
            "authority_context_id": first_client.authority_context_id,
            "last_registry_srv_created": 1,
            "last_registry_srv_modified": 1,
            "capability": {
                "supported": True,
                "security_enabled": True,
                "read": True,
                "create": True,
            },
        })

        second_transport = AuthorizationTransport(identity=self.rig_identity)
        second_client = NightscoutDeviceAuthorizationClient(
            "https://second.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            state_path,
            transport=second_transport,
        )
        runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
        runtime.client = second_client

        self.assertFalse(second_client.carrier_ready())
        self.assertIsNone(
            runtime._cached_peer_result(self.phone_identity.credential_id)["peer"]
        )
        lookup = second_client.lookup_peer(self.phone_identity.credential_id, "phone")
        self.assertEqual(lookup["classification"], "inconclusive")
        self.assertIsNone(lookup["peer"])
        self.assertFalse(second_transport.requests)

    def test_http_v2_mutual_auth_and_signed_event_round_trip(self):
        phone = self.phone_identity
        rig = self.rig_identity
        replay = InMemoryReplay()

        class Trust(object):
            def peer(self, credential_id):
                return {"credential_id": credential_id} if credential_id == phone.credential_id else None

            def record_direct_contact(self, credential_id):
                self.last_direct_contact = credential_id

        class Client(object):
            def __init__(self):
                self.trust = Trust()

        class Runtime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = Client()
            last_state = {"classification": "present"}

            def ensure_shadow_carrier_ready(self):
                return True

            def lookup_peer(self, credential_id, device_kind):
                if credential_id != phone.credential_id or device_kind != "phone":
                    return {"classification": "absent", "peer": None, "duplicate_state": "inconclusive"}
                return {
                    "classification": "present_cached",
                    "peer": {"public_key_der": phone.public_key_der},
                    "duplicate_state": "one_live_non_authoritative",
                }

            @staticmethod
            def consume_replay(kind, credential_id, message_id, ack_digest=None):
                return replay.consume(kind, credential_id, message_id, ack_digest)

        config = {
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
            "db_path": os.path.join(self.tmp, "events.sqlite3"),
            "auth_token": "legacy-token-placeholder",
            "materialize_temp_targets": False,
            "materialize_carbs": False,
        }
        handler = make_handler(config, authorization_runtime=Runtime())
        server = ThreadedHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        try:
            for method, path in (
                ("GET", "/v2/auth/challenge"),
                ("POST", "/v2/auth/session"),
                ("POST", "/v2/events"),
            ):
                connection = HTTPConnection("127.0.0.1", server.server_address[1])
                connection.request(
                    method,
                    path,
                    body="{}" if method == "POST" else None,
                    headers={"Content-Type": "application/json"},
                )
                unauthorized = connection.getresponse()
                unauthorized_payload = json.loads(
                    unauthorized.read().decode("utf-8")
                )
                connection.close()
                self.assertEqual(unauthorized.status, 401, path)
                self.assertEqual(unauthorized_payload.get("error"), "unauthorized", path)

            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request(
                "GET",
                "/v2/auth/challenge",
                headers={"Authorization": "Bearer legacy-token-placeholder"},
            )
            response = connection.getresponse()
            challenge = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)

            hello = build_auth_hello(
                phone,
                rig.credential_id,
                challenge["rig_challenge"],
                phone_challenge=b"p" * 32,
                message_id="11111111-1111-4111-8111-111111111111",
            )
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request(
                "POST", "/v2/auth/session", body=json.dumps(hello),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer legacy-token-placeholder",
                },
            )
            response = connection.getresponse()
            auth_ack = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)
            verify_auth_ack(auth_ack, hello, rig.public_key_der, phone)

            event = {
                "schema": "openaps.local.event.v1",
                "event_id": "event-placeholder",
                "patient_id": "patient-placeholder",
                "created_at": "2026-04-28T00:00:00Z",
                "effective_at": "2026-04-28T00:00:00Z",
                "created_by_phone_id": "phone-placeholder",
                "source": "ios",
                "event_type": "temp_target",
                "payload": {
                    "target_bottom_mgdl": 110,
                    "target_top_mgdl": 110,
                    "duration_minutes": 30,
                    "reason": None,
                    "notes": None,
                },
                "supersedes_event_id": None,
                "signature": None,
            }
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request(
                "POST",
                "/v1/events",
                body=json.dumps({"events": [event]}),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer legacy-token-placeholder",
                },
            )
            response = connection.getresponse()
            legacy_response = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(legacy_response["acks"][0]["ack_status"], "stored")
            self.assertIsNotNone(handler.db.get_event(event["event_id"]))
            legacy_ack_bytes = json.dumps(
                legacy_response["acks"][0],
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            counts_before_shadow = handler.db.counts()

            class LegacyBridgeRuntime(object):
                mode = "legacy"
                identity = None
                credential_id = None
                client = None
                carrier_ready_cached = False
                last_state = {"classification": "legacy"}

            bridge_config = dict(config)
            bridge_config["ble_http_base_url"] = "http://127.0.0.1:%d" % (
                server.server_address[1],
            )
            observation_bridge = RigBridge(
                bridge_config,
                authorization_runtime=LegacyBridgeRuntime(),
            )
            validated_event = ble_server_module.validate_event(event)
            expected_ack_sha256 = ble_server_module.hashlib.sha256(
                legacy_ack_bytes
            ).hexdigest()
            self.assertEqual(
                observation_bridge._persisted_legacy_observation(
                    validated_event,
                    expected_ack_sha256,
                ),
                legacy_ack_bytes,
            )
            with self.assertRaises(AuthorizationError):
                observation_bridge._persisted_legacy_observation(
                    validated_event,
                    "0" * 64,
                )

            signed_event = build_signed_event(
                phone,
                auth_ack["session_id"],
                rig.credential_id,
                event["event_id"],
                json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                legacy_ack_bytes,
                nonce=b"n" * 32,
            )
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request(
                "POST", "/v2/events", body=json.dumps(signed_event),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer legacy-token-placeholder",
                },
            )
            response = connection.getresponse()
            signed_ack = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)
            ack_payload = json.loads(validate_signed_ack(
                signed_ack,
                rig.public_key_der,
                phone,
            ).decode("utf-8"))
            self.assertEqual(ack_payload["schema"], "openaps.authorization-shadow-observation.v1")
            self.assertEqual(ack_payload["verification_status"], "verified")
            self.assertEqual(ack_payload["event_id"], event["event_id"])
            self.assertEqual(
                base64.b64decode(ack_payload["legacy_ack"]),
                legacy_ack_bytes,
            )
            self.assertEqual(
                ack_payload["legacy_ack_sha256"],
                signed_event["legacy_ack_sha256"],
            )
            self.assertEqual(handler.db.counts(), counts_before_shadow)

            mismatched_event = json.loads(json.dumps(event))
            mismatched_event["payload"]["duration_minutes"] = 45
            mismatched_signed_event = build_signed_event(
                phone,
                auth_ack["session_id"],
                rig.credential_id,
                event["event_id"],
                json.dumps(
                    mismatched_event,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
                legacy_ack_bytes,
                nonce=b"m" * 32,
            )
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request(
                "POST",
                "/v2/events",
                body=json.dumps(mismatched_signed_event),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer legacy-token-placeholder",
                },
            )
            response = connection.getresponse()
            mismatch_response = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 401)
            self.assertEqual(mismatch_response["error"], "authorization_failed")

            wrong_ack_signed_event = build_signed_event(
                phone,
                auth_ack["session_id"],
                rig.credential_id,
                event["event_id"],
                json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                b'{"ack_status":"stored","event_id":"wrong"}',
                nonce=b"w" * 32,
            )
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request(
                "POST",
                "/v2/events",
                body=json.dumps(wrong_ack_signed_event),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer legacy-token-placeholder",
                },
            )
            response = connection.getresponse()
            wrong_ack_response = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 401)
            self.assertEqual(wrong_ack_response["error"], "authorization_failed")
            self.assertEqual(handler.db.counts(), counts_before_shadow)
        finally:
            server.shutdown()
            server.server_close()
            handler.db.close()

    def test_slow_http_shadow_auth_does_not_delay_or_mutate_legacy_health(self):
        phone = self.phone_identity
        rig = self.rig_identity
        replay = InMemoryReplay()
        lookup_started = threading.Event()
        release_lookup = threading.Event()

        class Trust(object):
            def peer(self, credential_id):
                return {"credential_id": credential_id}

            def record_direct_contact(self, _credential_id):
                return None

        class Client(object):
            trust = Trust()

        class Runtime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = Client()
            last_state = {"classification": "present"}

            @staticmethod
            def ensure_shadow_carrier_ready():
                return True

            @staticmethod
            def lookup_peer(credential_id, device_kind):
                lookup_started.set()
                if not release_lookup.wait(3):
                    raise RuntimeError("test lookup release timed out")
                return {
                    "classification": "present_cached",
                    "peer": {"public_key_der": phone.public_key_der},
                    "duplicate_state": "one_live_non_authoritative",
                }

            @staticmethod
            def consume_replay(kind, credential_id, message_id, ack_digest=None):
                return replay.consume(kind, credential_id, message_id, ack_digest)

        config = {
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
            "db_path": os.path.join(self.tmp, "responsive-events.sqlite3"),
            "auth_token": "legacy-token-placeholder",
            "authorization_http_max_inflight": 1,
            "materialize_temp_targets": False,
            "materialize_carbs": False,
        }
        handler = make_handler(config, authorization_runtime=Runtime())
        server = ThreadedHTTPServer(("127.0.0.1", 0), handler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        auth_outcome = {}
        auth_thread = None
        try:
            headers = {"Authorization": "Bearer legacy-token-placeholder"}
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("GET", "/v2/auth/challenge", headers=headers)
            response = connection.getresponse()
            challenge = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)
            hello = build_auth_hello(
                phone,
                rig.credential_id,
                challenge["rig_challenge"],
                phone_challenge=b"q" * 32,
                message_id="22222222-2222-4222-8222-222222222222",
            )

            def send_slow_auth():
                try:
                    connection = HTTPConnection("127.0.0.1", server.server_address[1])
                    connection.request(
                        "POST",
                        "/v2/auth/session",
                        body=json.dumps(hello),
                        headers={
                            "Authorization": "Bearer legacy-token-placeholder",
                            "Content-Type": "application/json",
                        },
                    )
                    response = connection.getresponse()
                    auth_outcome["status"] = response.status
                    response.read()
                    connection.close()
                except Exception as exc:
                    auth_outcome["error"] = exc

            auth_thread = threading.Thread(target=send_slow_auth)
            auth_thread.daemon = True
            auth_thread.start()
            self.assertTrue(lookup_started.wait(1))

            started_at = time.monotonic()
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("GET", "/v1/health", headers=headers)
            response = connection.getresponse()
            health = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertLess(time.monotonic() - started_at, 0.75)
            self.assertEqual(response.status, 200)
            self.assertTrue(health["ok"])
            self.assertEqual(handler.db.counts(), {"events": 0, "acks": 0})
        finally:
            release_lookup.set()
            if auth_thread is not None:
                auth_thread.join(2)
            server.shutdown()
            server.server_close()
            handler.db.close()
        self.assertNotIn("error", auth_outcome)
        self.assertEqual(auth_outcome.get("status"), 200)

    def test_concurrent_http_unknown_credential_flood_is_bounded_and_legacy_health_stays_fast(self):
        """Admission rejects a flood before expensive work and leaves legacy responsive."""
        rig = self.rig_identity

        class Trust(object):
            def peer(self, _credential_id):
                return None

        class Client(object):
            trust = Trust()

        class Runtime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = Client()
            last_state = {"classification": "present"}

            def ensure_shadow_carrier_ready(self):
                return False

        config = {
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
            "db_path": os.path.join(self.tmp, "admission-flood.sqlite3"),
            "auth_token": "legacy-token-placeholder",
            "authorization_http_max_inflight": 2,
            "materialize_temp_targets": False,
            "materialize_carbs": False,
        }
        handler = make_handler(config, authorization_runtime=Runtime())
        server = ThreadedHTTPServer(("127.0.0.1", 0), handler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        results = []
        results_lock = threading.Lock()
        start = threading.Event()

        try:
            headers = {
                "Authorization": "Bearer legacy-token-placeholder",
                "Content-Type": "application/json",
            }
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("GET", "/v2/auth/challenge", headers=headers)
            response = connection.getresponse()
            challenge = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)

            template = build_auth_hello(
                self.phone_identity,
                rig.credential_id,
                challenge["rig_challenge"],
                phone_challenge=b"f" * 32,
                message_id="00000000-0000-4000-8000-000000000001",
            )

            def flood(index):
                start.wait(2)
                hello = dict(template)
                # Distinct, syntactically valid credentials exercise the
                # bounded unknown-credential admission table.
                hello["phone_credential_id"] = "%064x" % (index + 1)
                try:
                    conn = HTTPConnection("127.0.0.1", server.server_address[1])
                    conn.request("POST", "/v2/auth/session", body=json.dumps(hello), headers=headers)
                    reply = conn.getresponse()
                    reply.read()
                    status = reply.status
                    conn.close()
                except Exception as exc:
                    status = exc
                with results_lock:
                    results.append(status)

            workers = [threading.Thread(target=flood, args=(index,)) for index in range(32)]
            for worker in workers:
                worker.daemon = True
                worker.start()
            started_at = time.monotonic()
            start.set()
            for worker in workers:
                worker.join(5)
            self.assertEqual(len(results), len(workers))
            self.assertFalse([value for value in results if not isinstance(value, int)])
            self.assertTrue(set(results).issubset(set([401, 429])))
            # Both outcomes are bounded rejections. A fast source-failure
            # guard can reject the entire burst as 401 before the bounded
            # worker semaphore has an opportunity to return 429; requiring a
            # particular mix makes the concurrency test scheduler-dependent.
            self.assertTrue(results)

            started_at = time.monotonic()
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("GET", "/v1/health", headers=headers)
            response = connection.getresponse()
            health = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertLess(time.monotonic() - started_at, 0.75)
            self.assertEqual(response.status, 200)
            self.assertTrue(health["ok"])
        finally:
            server.shutdown()
            server.server_close()
            handler.db.close()

    def test_threaded_http_preserves_serial_legacy_event_processing(self):
        config = {
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
            "db_path": os.path.join(self.tmp, "serialized-events.sqlite3"),
            "auth_token": "legacy-token-placeholder",
            "materialize_temp_targets": False,
            "materialize_carbs": False,
        }
        handler = make_handler(config)
        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()
        observation_lock = threading.Lock()
        observation = {"calls": 0, "active": 0, "maximum_active": 0}

        def observed_process(_self, _events, log_prefix="POST /v1/events"):
            with observation_lock:
                observation["calls"] += 1
                call_number = observation["calls"]
                observation["active"] += 1
                observation["maximum_active"] = max(
                    observation["maximum_active"],
                    observation["active"],
                )
            if call_number == 1:
                first_entered.set()
                if not release_first.wait(3):
                    raise RuntimeError("test legacy release timed out")
            else:
                second_entered.set()
            with observation_lock:
                observation["active"] -= 1
            return []

        handler._process_events = observed_process
        server = ThreadedHTTPServer(("127.0.0.1", 0), handler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        results = []

        def send_legacy_request():
            try:
                connection = HTTPConnection("127.0.0.1", server.server_address[1])
                connection.request(
                    "POST",
                    "/v1/events",
                    body=json.dumps({"events": []}),
                    headers={
                        "Authorization": "Bearer legacy-token-placeholder",
                        "Content-Type": "application/json",
                    },
                )
                response = connection.getresponse()
                response.read()
                results.append(response.status)
                connection.close()
            except Exception as exc:
                results.append(exc)

        first = threading.Thread(target=send_legacy_request)
        second = threading.Thread(target=send_legacy_request)
        first.daemon = True
        second.daemon = True
        try:
            first.start()
            self.assertTrue(first_entered.wait(1))
            second.start()
            self.assertFalse(second_entered.wait(0.2))
            with observation_lock:
                self.assertEqual(observation["maximum_active"], 1)
        finally:
            release_first.set()
            first.join(2)
            second.join(2)
            server.shutdown()
            server.server_close()
            handler.db.close()
        self.assertTrue(second_entered.is_set())
        self.assertEqual(observation["maximum_active"], 1)
        self.assertEqual(sorted(results), [200, 200])

    def test_ble_signed_event_is_observational_and_does_not_post_legacy_event(self):
        phone = self.phone_identity
        rig = self.rig_identity
        replay = InMemoryReplay()

        class Trust(object):
            def __init__(self):
                self.direct_contacts = []

            def record_direct_contact(self, credential_id):
                self.direct_contacts.append(credential_id)

        class Client(object):
            def __init__(self):
                self.trust = Trust()

        class Runtime(object):
            mode = "shadow"
            identity = rig
            credential_id = rig.credential_id
            client = Client()
            last_state = {"classification": "present"}

            def start_periodic_reconciliation(self):
                return None

            @staticmethod
            def consume_replay(kind, credential_id, message_id, ack_digest=None):
                return replay.consume(kind, credential_id, message_id, ack_digest)

        config = {
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.tmp,
            "ble_require_auth": True,
            "ble_auth_token": "ble-token-placeholder",
        }
        runtime = Runtime()
        bridge = RigBridge(config, authorization_runtime=runtime)
        connection_id = "connection-placeholder"
        rig.cache_peer_public_key(phone.credential_id, phone.public_key_der)
        session_id = bridge.authorization_sessions.create(
            phone.credential_id,
            rig.credential_id,
            connection_id=connection_id,
        )
        event = {
            "schema": "openaps.local.event.v1",
            "event_id": "ble-event-placeholder",
            "patient_id": "patient-placeholder",
            "created_at": "2026-04-28T00:00:00Z",
            "effective_at": "2026-04-28T00:00:00Z",
            "created_by_phone_id": "phone-placeholder",
            "source": "ios",
            "event_type": "temp_target",
            "payload": {
                "target_bottom_mgdl": 110,
                "target_top_mgdl": 110,
                "duration_minutes": 30,
                "reason": None,
                "notes": None,
            },
            "supersedes_event_id": None,
            "signature": None,
        }
        event_bytes = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        legacy_ack_bytes = json.dumps({
            "schema": "openaps.local.event_ack.v1",
            "event_id": event["event_id"],
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "ack_status": "stored",
            "received_at": "2026-04-28T00:00:01Z",
            "details": {"duplicate": False, "materialization": "stored_not_materialized"},
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signed_event = build_signed_event(
            phone,
            session_id,
            rig.credential_id,
            event["event_id"],
            event_bytes,
            legacy_ack_bytes,
            nonce=b"b" * 32,
        )
        signed_bytes = json.dumps(
            signed_event,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        chunks = [signed_bytes[offset:offset + 512] for offset in range(0, len(signed_bytes), 512)]
        legacy_posts = []

        def unexpected_legacy_post(legacy_event):
            legacy_posts.append(legacy_event)
            raise AssertionError("signed shadow path must not deliver the legacy event")

        def persisted_legacy_observation(_validated, expected_sha256):
            if expected_sha256 != signed_event["legacy_ack_sha256"]:
                raise AuthorizationError("legacy ACK mismatch")
            return legacy_ack_bytes

        bridge.post_event = unexpected_legacy_post
        bridge._persisted_legacy_observation = persisted_legacy_observation
        signed_ack = None
        for index, chunk in enumerate(chunks):
            envelope = {
                "envelope_version": 1,
                "message_id": event["event_id"],
                "seq": index,
                "total": len(chunks),
                "encoding": "base64",
                "payload": base64.b64encode(chunk).decode("ascii"),
                "auth_token": "ble-token-placeholder",
            }
            signed_ack = bridge.submit_ble_write(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                connection_id=connection_id,
            )
            if index + 1 < len(chunks):
                self.assertIsNone(signed_ack)

        observation = json.loads(validate_signed_ack(
            signed_ack,
            rig.public_key_der,
            phone,
        ).decode("utf-8"))
        self.assertEqual(observation["schema"], "openaps.authorization-shadow-observation.v1")
        self.assertEqual(observation["verification_status"], "verified")
        self.assertTrue(observation["legacy_delivery_required"])
        self.assertEqual(base64.b64decode(observation["legacy_ack"]), legacy_ack_bytes)
        self.assertFalse(legacy_posts)
        self.assertEqual(runtime.client.trust.direct_contacts, [phone.credential_id])

    def test_runtime_keeps_nightscout_confirmed_peer_usable_offline(self):
        phone = self.phone_identity
        lookup_started = threading.Event()
        release_lookup = threading.Event()

        class Trust(object):
            def peer(self, credential_id):
                if credential_id != phone.credential_id:
                    return None
                return {
                    "credential_id": credential_id,
                    "public_key_der": base64.b64encode(phone.public_key_der).decode("ascii"),
                    "registry_duplicate_state": "one_live_non_authoritative",
                }

            def self_state(self):
                return {
                    "classification": "present",
                    "capability": {"supported": True},
                }

        class OfflineClient(object):
            trust = Trust()

            def lookup_peer(self, credential_id, device_kind):
                lookup_started.set()
                release_lookup.wait(2)
                raise NightscoutAuthorizationError("offline")

        runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
        runtime.client = OfflineClient()
        runtime._lookup_lock = threading.Lock()
        runtime._lookup_inflight = {}
        started = time.monotonic()
        result = runtime.lookup_peer(phone.credential_id, "phone")
        elapsed = time.monotonic() - started
        self.assertEqual(result["classification"], "present_cached")
        self.assertEqual(result["peer"]["public_key_der"], phone.public_key_der)
        self.assertLess(elapsed, 0.5)
        self.assertTrue(lookup_started.wait(0.5))
        release_lookup.set()

    def test_runtime_classifies_legacy_api_secret_without_attempting_registry(self):
        runtime = AuthorizationRuntime({
            "authorization_mode": "shadow",
            "authorization_identity_dir": os.path.join(self.tmp, "legacy-secret-identity"),
            "nightscout_host": "https://diyps.example.invalid",
            "nightscout_access_token": None,
            "nightscout_credential_kind": "legacy_api_secret",
            "authorization_state_path": os.path.join(self.tmp, "legacy-secret-state.json"),
            "authorization_openssl_path": "/usr/bin/openssl",
        })
        self.assertIsNotNone(runtime.identity)
        self.assertIsNone(runtime.client)
        self.assertEqual(runtime.last_state["classification"], "legacy_api_secret_unsupported")

    def test_runtime_configuration_is_a_private_startup_snapshot(self):
        config = {"authorization_mode": "legacy",
            "nightscout_host": "https://example.invalid/base",
            "nightscout_access_token": "synthetic-first"}
        runtime = AuthorizationRuntime(config)
        config["nightscout_host"] = "https://example.invalid/other"
        config["nightscout_access_token"] = "synthetic-second"
        config["authorization_mode"] = "shadow"
        self.assertEqual(runtime.config["nightscout_host"], "https://example.invalid/base")
        self.assertEqual(runtime.config["nightscout_access_token"], "synthetic-first")
        self.assertEqual(runtime.mode, "legacy")
        with self.assertRaises(TypeError):
            runtime.config["nightscout_host"] = "https://example.invalid/other"

    def test_runtime_proof_preparation_is_network_free_and_https_only(self):
        from openaps_locald.proof_http_transport import BoundedProofTransport
        for scheme in ("https", "http"):
            for secret_mode in (False, True):
                config = {"authorization_mode": "legacy",
                    "nightscout_host": scheme + "://example.invalid/base",
                    "nightscout_api_secret" if secret_mode else "nightscout_access_token": "synthetic"}
                runtime = AuthorizationRuntime(config)
                runtime.identity = DeviceIdentity(os.path.join(self.tmp,
                    "proof-preparation-" + scheme + str(secret_mode)))
                with patch.object(BoundedProofTransport, "request_bytes",
                        side_effect=AssertionError("preparation must not send requests")) as request:
                    runtime._prepare_proof_client()
                    first = runtime._proof_client
                    runtime._prepare_proof_client()
                    self.assertIs(runtime._proof_client, first)
                    self.assertFalse(request.called)
                self.assertEqual(first is not None, scheme == "https")
                self.assertIsNone(runtime.client)
                self.assertFalse(runtime.carrier_ready_cached)

        config = {"authorization_mode": "legacy",
            "nightscout_host": "http://example.invalid:57257/base",
            "nightscout_access_token": "synthetic", "allow_legacy_http_proof": True}
        runtime = AuthorizationRuntime(config)
        runtime.identity = DeviceIdentity(os.path.join(self.tmp, "proof-preparation-explicit-http"))
        with patch.object(BoundedProofTransport, "request_bytes",
                side_effect=AssertionError("preparation must not send requests")) as request:
            runtime._prepare_proof_client()
            self.assertIsNotNone(runtime._proof_client)
            self.assertFalse(request.called)

    def test_runtime_proof_close_retains_live_owner_and_prevents_recreation(self):
        runtime = AuthorizationRuntime({"authorization_mode": "legacy"})
        class Owner:
            terminal = False
            cancelled = 0
            def invalidate(self):
                self.cancelled += 1
            def reap_cancelled_network_worker(self):
                return self.terminal
        owner = Owner()
        runtime._proof_client = owner
        self.assertFalse(runtime.close_proof_owner())
        self.assertIs(runtime._proof_client, owner)
        self.assertEqual(owner.cancelled, 1)
        owner.terminal = True
        self.assertTrue(runtime.close_proof_owner())
        self.assertIsNone(runtime._proof_client)
        runtime.identity = object()
        runtime._prepare_proof_client()
        self.assertIsNone(runtime._proof_client)
        self.assertTrue(runtime.close_proof_owner())

    def test_runtime_proof_close_during_preparation_is_nonblocking_and_sticky(self):
        runtime = AuthorizationRuntime({"authorization_mode": "legacy"})
        runtime._proof_lock.acquire()
        try:
            self.assertFalse(runtime.close_proof_owner())
        finally:
            runtime._proof_lock.release()
        runtime.identity = object()
        runtime._prepare_proof_client()
        self.assertIsNone(runtime._proof_client)
        self.assertTrue(runtime.close_proof_owner())

    def test_background_runtime_initialization_never_blocks_or_escapes_io_failure(self):
        identity_started = threading.Event()
        release_identity = threading.Event()
        original_identity = authorization_runtime_module.DeviceIdentity

        class SlowBrokenIdentity(object):
            def __init__(self, *_args, **_kwargs):
                identity_started.set()
                if not release_identity.wait(3):
                    raise RuntimeError("test identity release timed out")
                raise OSError("simulated shadow identity I/O failure")

        authorization_runtime_module.DeviceIdentity = SlowBrokenIdentity
        try:
            started_at = time.monotonic()
            runtime = AuthorizationRuntime({
                "authorization_mode": "shadow",
                "authorization_identity_dir": os.path.join(self.tmp, "slow-identity"),
                "nightscout_host": "https://diyps.example.invalid",
                "nightscout_access_token": "access-placeholder",
                "authorization_state_path": os.path.join(self.tmp, "slow-state.json"),
            }, initialize_in_background=True)
            self.assertLess(time.monotonic() - started_at, 0.25)
            self.assertTrue(identity_started.wait(1))
            self.assertEqual(runtime.last_state["classification"], "initializing")
            release_identity.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with runtime._initialization_lock:
                    if not runtime._initialization_inflight:
                        break
                time.sleep(0.005)
            else:
                self.fail("background authorization initialization did not finish")
            self.assertIsNone(runtime.identity)
            self.assertIsNone(runtime.client)
            self.assertEqual(runtime.last_state["classification"], "initialization_error")
            self.assertEqual(runtime.last_state["error_category"], "identity_unexpected")
        finally:
            release_identity.set()
            authorization_runtime_module.DeviceIdentity = original_identity

    def test_runtime_reconcile_failure_is_monotonically_throttled(self):
        clock = FakeClock(1000)

        class Client(object):
            authority_context_id = "ns_" + ("a" * 64)

            def __init__(self):
                self.calls = 0

            def reconcile_self(self):
                self.calls += 1
                return {
                    "classification": "error",
                    "authority_context_id": self.authority_context_id,
                    "credential_id": "b" * 64,
                    "capability": {},
                }

        class Identity(object):
            credential_id = "b" * 64

        client = Client()
        runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
        runtime.mode = "shadow"
        runtime.identity = Identity()
        runtime.client = client
        runtime.carrier_ready_cached = False
        runtime.last_state = {"classification": "initialized"}
        runtime._monotonic = clock
        runtime._reconcile_async_lock = threading.Lock()
        runtime._reconcile_async_inflight = False
        runtime._reconcile_last_started = None
        runtime._reconcile_refresh_interval = 0

        def wait_until_idle():
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with runtime._reconcile_async_lock:
                    if not runtime._reconcile_async_inflight:
                        return
                time.sleep(0.005)
            self.fail("runtime reconcile did not finish")

        self.assertFalse(runtime.ensure_shadow_carrier_ready())
        wait_until_idle()
        self.assertEqual(client.calls, 1)
        self.assertFalse(runtime.ensure_shadow_carrier_ready())
        self.assertEqual(client.calls, 1)
        clock.advance(5 * 60 + 1)
        self.assertFalse(runtime.ensure_shadow_carrier_ready())
        wait_until_idle()
        self.assertEqual(client.calls, 2)

    def test_runtime_ambiguous_create_uses_six_hour_refresh_cadence(self):
        clock = FakeClock(2000)

        class Client(object):
            authority_context_id = "ns_" + ("c" * 64)

            def __init__(self):
                self.calls = 0

            def reconcile_self(self):
                self.calls += 1
                return {
                    "classification": "ambiguous_create",
                    "authority_context_id": self.authority_context_id,
                    "credential_id": "d" * 64,
                    "ambiguous_create_srv_date": 1893553445000,
                    "capability": {
                        "supported": True,
                        "security_enabled": True,
                        "read": True,
                        "create": True,
                    },
                }

        class Identity(object):
            credential_id = "d" * 64

        client = Client()
        runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
        runtime.mode = "shadow"
        runtime.identity = Identity()
        runtime.client = client
        runtime.carrier_ready_cached = False
        runtime.last_state = {"classification": "initialized"}
        runtime._monotonic = clock
        runtime._reconcile_async_lock = threading.Lock()
        runtime._reconcile_async_inflight = False
        runtime._reconcile_last_started = None
        runtime._reconcile_refresh_interval = 0

        def wait_until_idle():
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with runtime._reconcile_async_lock:
                    if not runtime._reconcile_async_inflight:
                        return
                time.sleep(0.005)
            self.fail("runtime ambiguous reconcile did not finish")

        self.assertFalse(runtime.ensure_shadow_carrier_ready())
        wait_until_idle()
        self.assertEqual(client.calls, 1)
        clock.advance(5 * 60 + 1)
        self.assertFalse(runtime.ensure_shadow_carrier_ready())
        self.assertEqual(client.calls, 1)
        clock.advance(6 * 60 * 60)
        self.assertFalse(runtime.ensure_shadow_carrier_ready())
        wait_until_idle()
        self.assertEqual(client.calls, 2)

    def test_peer_refresh_thread_start_failure_clears_singleflight(self):
        class Client(object):
            @staticmethod
            def lookup_peer(_credential_id, _device_kind):
                raise AssertionError("refresh body must not run when thread start fails")

        class BrokenThread(object):
            def __init__(self, *args, **kwargs):
                self.daemon = False

            @staticmethod
            def start():
                raise RuntimeError("simulated thread start failure")

        runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
        runtime.client = Client()
        runtime._lookup_lock = threading.Lock()
        runtime._lookup_inflight = {}
        runtime._lookup_last_started = {}
        runtime._lookup_refresh_intervals = {}
        runtime._monotonic = FakeClock(2000)
        credential_id = "c" * 64
        original_thread = authorization_runtime_module.threading.Thread
        authorization_runtime_module.threading.Thread = BrokenThread
        try:
            runtime._refresh_cached_peer_async(
                credential_id,
                "phone",
                cached_positive=False,
            )
        finally:
            authorization_runtime_module.threading.Thread = original_thread
        self.assertNotIn(credential_id, runtime._lookup_inflight)
        self.assertEqual(
            runtime._lookup_refresh_intervals[credential_id],
            5 * 60,
        )

    def test_cached_positive_peer_refresh_uses_six_hour_success_cadence(self):
        authority = realm_id_for_nightscout("https://cadence.example.invalid")
        phone = self.phone_identity
        clock = FakeClock(1000)

        class Trust(object):
            def peer(self, credential_id):
                if credential_id != phone.credential_id:
                    return None
                return {
                    "authority_context_id": authority,
                    "credential_id": credential_id,
                    "public_key_der": base64.b64encode(phone.public_key_der).decode("ascii"),
                    "registry_duplicate_state": "one_live_non_authoritative",
                }

        class Client(object):
            authority_context_id = authority
            trust = Trust()

            def __init__(self, fail=False):
                self.calls = 0
                self.fail = fail

            def lookup_peer(self, credential_id, device_kind):
                self.calls += 1
                if self.fail:
                    raise NightscoutAuthorizationError("offline")
                return {"classification": "present", "peer": {}, "duplicate_state": "inconclusive"}

        def runtime_for(client, local_clock):
            runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
            runtime.client = client
            runtime._lookup_lock = threading.Lock()
            runtime._lookup_inflight = {}
            runtime._monotonic = local_clock
            return runtime

        def wait_until_idle(runtime):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with runtime._lookup_lock:
                    if not runtime._lookup_inflight:
                        return
                time.sleep(0.005)
            self.fail("peer refresh did not finish")

        client = Client()
        runtime = runtime_for(client, clock)
        self.assertEqual(
            runtime.lookup_peer(phone.credential_id, "phone")["classification"],
            "present_cached",
        )
        wait_until_idle(runtime)
        self.assertEqual(client.calls, 1)
        clock.advance(5 * 60 + 1)
        runtime.lookup_peer(phone.credential_id, "phone")
        self.assertEqual(client.calls, 1)
        clock.advance(6 * 60 * 60 - (5 * 60 + 1))
        runtime.lookup_peer(phone.credential_id, "phone")
        wait_until_idle(runtime)
        self.assertEqual(client.calls, 2)

        failure_clock = FakeClock(2000)
        failing_client = Client(fail=True)
        failing_runtime = runtime_for(failing_client, failure_clock)
        failing_runtime.lookup_peer(phone.credential_id, "phone")
        wait_until_idle(failing_runtime)
        self.assertEqual(failing_client.calls, 1)
        failure_clock.advance(5 * 60 - 1)
        failing_runtime.lookup_peer(phone.credential_id, "phone")
        self.assertEqual(failing_client.calls, 1)
        failure_clock.advance(2)
        failing_runtime.lookup_peer(phone.credential_id, "phone")
        wait_until_idle(failing_runtime)
        self.assertEqual(failing_client.calls, 2)

    def test_peer_refresh_history_is_bounded_under_unknown_credentials(self):
        clock = FakeClock(3000)

        class Client(object):
            def lookup_peer(self, credential_id, device_kind):
                return {"classification": "absent", "peer": None, "duplicate_state": "inconclusive"}

        runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
        runtime.client = Client()
        runtime._lookup_lock = threading.Lock()
        runtime._lookup_inflight = {}
        runtime._monotonic = clock
        credentials = ["%064x" % value for value in range(1, 141)]
        for credential_id in credentials:
            runtime._refresh_cached_peer_async(
                credential_id,
                "phone",
                cached_positive=False,
            )
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with runtime._lookup_lock:
                    if credential_id not in runtime._lookup_inflight:
                        break
                time.sleep(0.001)
            else:
                self.fail("unknown peer refresh did not finish")
        self.assertEqual(len(runtime._lookup_last_started), 128)
        self.assertEqual(len(runtime._lookup_refresh_intervals), 128)
        self.assertNotIn(credentials[0], runtime._lookup_last_started)
        self.assertIn(credentials[-1], runtime._lookup_last_started)
        clock.advance(5 * 60 + 1)
        runtime._refresh_cached_peer_async(
            "%064x" % 1000,
            "phone",
            cached_positive=False,
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with runtime._lookup_lock:
                if not runtime._lookup_inflight:
                    break
            time.sleep(0.001)
        self.assertEqual(len(runtime._lookup_last_started), 1)
        self.assertEqual(len(runtime._lookup_refresh_intervals), 1)

    def test_nightscout_negative_cache_is_bounded_lru_and_prunes_expired(self):
        clock = FakeClock(4000)
        client = NightscoutDeviceAuthorizationClient(
            "https://negative-cache.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "negative-cache-state.json"),
            transport=AuthorizationTransport(identity=self.rig_identity),
            monotonic=clock,
        )
        credentials = ["%064x" % value for value in range(1, 130)]
        for credential_id in credentials[:128]:
            client._remember_negative_cache(credential_id, clock() + 5 * 60)
        self.assertTrue(client._negative_cache_hit(credentials[0]))
        client._remember_negative_cache(credentials[128], clock() + 5 * 60)
        self.assertEqual(len(client._negative_cache), 128)
        self.assertNotIn(credentials[1], client._negative_cache)
        self.assertIn(credentials[0], client._negative_cache)
        self.assertIn(credentials[128], client._negative_cache)
        clock.advance(5 * 60 + 1)
        self.assertFalse(client._negative_cache_hit(credentials[0]))
        self.assertFalse(client._negative_cache)

    def test_peer_verifier_never_holds_shared_trust_store_lock(self):
        authority_url = "https://nonblocking-trust.example.invalid"
        client = NightscoutDeviceAuthorizationClient(
            authority_url,
            "access-placeholder",
            self.rig_identity,
            "rig",
            os.path.join(self.tmp, "nonblocking-trust-state.json"),
            transport=AuthorizationTransport(identity=self.rig_identity),
        )
        client.trust.record_self({
            "classification": "present",
            "duplicate_state": "one_live_non_authoritative",
            "last_registry_srv_created": 1,
            "last_registry_srv_modified": 1,
            "capability": {
                "supported": True,
                "security_enabled": True,
                "read": True,
                "create": True,
            },
        })
        authority = realm_id_for_nightscout(authority_url)
        peer = {
            "credential_id": self.phone_identity.credential_id,
            "device_kind": "phone",
            "realm_id": authority,
            "registry_identifier": registry_identifier(self.phone_identity.credential_id),
            "public_key_der": self.phone_identity.public_key_der,
            "nightscout_subject": "subject-placeholder",
            "srv_created": 1,
            "srv_modified": 1,
        }
        verifier_entered = threading.Event()
        release_verifier = threading.Event()
        reader_done = threading.Event()
        reader_results = []
        writer_errors = []
        original_validator = nightscout_authorization_module.validate_public_key_der

        def slow_validator(*args, **kwargs):
            verifier_entered.set()
            if not release_verifier.wait(5):
                raise RuntimeError("test verifier release timed out")
            return original_validator(*args, **kwargs)

        def write_peer():
            try:
                client.trust.record_peer_confirmation(
                    peer,
                    "one_live_non_authoritative",
                )
            except Exception as exc:
                writer_errors.append(exc)

        def read_carrier_state():
            reader_results.append(client.carrier_ready())
            reader_done.set()

        nightscout_authorization_module.validate_public_key_der = slow_validator
        writer = threading.Thread(target=write_peer)
        reader = threading.Thread(target=read_carrier_state)
        writer.daemon = True
        reader.daemon = True
        try:
            writer.start()
            self.assertTrue(verifier_entered.wait(1))
            reader.start()
            read_completed_before_release = reader_done.wait(1)
        finally:
            release_verifier.set()
            writer.join(5)
            reader.join(5)
            nightscout_authorization_module.validate_public_key_der = original_validator
        self.assertTrue(read_completed_before_release)
        self.assertEqual(reader_results, [True])
        self.assertFalse(writer_errors)

    def test_shadow_trust_store_migrates_v1_idempotently_and_remains_offline_ready(self):
        path = os.path.join(self.tmp, "migrated-shadow-state.json")
        authority = realm_id_for_nightscout("https://authority-a.example.invalid")
        peer_record = self._persisted_peer_record(authority)
        legacy = {
            "schema": "openaps.auth-shadow-state.v1",
            "peers": {self.phone_identity.credential_id: peer_record},
            "self": self._legacy_self_state(authority),
        }
        with open(path, "w") as handle:
            json.dump(legacy, handle, sort_keys=True, separators=(",", ":"))

        migrated = self._scoped_trust_store(path, authority)
        migrated_peer = migrated.peer(self.phone_identity.credential_id)
        migrated_self = migrated.self_state()
        self.assertEqual(
            migrated_peer["candidate_revocation"],
            peer_record["candidate_revocation"],
        )
        self.assertEqual(migrated_peer["last_direct_contact_at"], 1002.0)
        self.assertEqual(migrated_self["credential_id"], self.rig_identity.credential_id)
        self.assertEqual(migrated_self["device_kind"], "rig")
        self.assertEqual(migrated_self["realm_id"], authority)
        self.assertEqual(migrated_self["protocol_version"], 1)
        self.assertEqual(
            migrated_self["registry_identifier"],
            registry_identifier(self.rig_identity.credential_id),
        )
        self.assertFalse(any(migrated.quarantine_state().values()))
        with open(path, "rb") as handle:
            first_v2_bytes = handle.read()

        offline_client = NightscoutDeviceAuthorizationClient(
            "https://authority-a.example.invalid",
            "access-placeholder",
            self.rig_identity,
            "rig",
            path,
            transport=AuthorizationTransport(identity=self.rig_identity),
        )
        self.assertTrue(offline_client.carrier_ready())
        self.assertIsNotNone(
            offline_client.trust.peer(self.phone_identity.credential_id)
        )
        with open(path, "rb") as handle:
            second_v2_bytes = handle.read()
        self.assertEqual(second_v2_bytes, first_v2_bytes)
        with open(path, "r") as handle:
            persisted = json.load(handle)
        expected_self_key = authority + ":" + self.rig_identity.credential_id
        expected_peer_key = authority + ":" + self.phone_identity.credential_id
        self.assertEqual(persisted["schema"], "openaps.auth-shadow-state.v2")
        self.assertEqual(set(persisted["self"]), set([expected_self_key]))
        self.assertEqual(set(persisted["peers"]), set([expected_peer_key]))

    def test_metadata_less_cached_peer_is_quarantined_then_refreshed(self):
        path = os.path.join(self.tmp, "metadata-revalidation-state.json")
        base_url = "https://metadata-revalidation.example.invalid"
        authority = realm_id_for_nightscout(base_url)
        stale_peer = self._persisted_peer_record(authority)
        stale_peer.pop("last_registry_srv_created")
        stale_peer.pop("last_registry_srv_modified")
        with open(path, "w") as handle:
            json.dump({
                "schema": "openaps.auth-shadow-state.v1",
                "peers": {self.phone_identity.credential_id: stale_peer},
                "self": self._legacy_self_state(authority),
            }, handle, sort_keys=True, separators=(",", ":"))

        store = self._scoped_trust_store(path, authority)
        self.assertIsNone(store.peer(self.phone_identity.credential_id))
        self.assertEqual(len(store.quarantine_state()["peers"]), 1)

        transport = AuthorizationTransport(identity=self.rig_identity)
        document = build_enrollment_record(
            self.phone_identity,
            "phone",
            base_url,
            transport.server_date,
            nonce=b"u" * 32,
        )
        identifier = registry_identifier(self.phone_identity.credential_id)
        document.update({
            "identifier": identifier,
            "subject": transport.subject,
            "srvCreated": transport.server_date,
            "srvModified": transport.server_date + 1,
        })
        transport.documents[identifier] = document
        client = NightscoutDeviceAuthorizationClient(
            base_url,
            "access-placeholder",
            self.rig_identity,
            "rig",
            path,
            transport=transport,
        )

        refreshed = client.lookup_peer(self.phone_identity.credential_id, "phone")

        self.assertEqual(refreshed["classification"], "present")
        cached_peer = client.trust.peer(self.phone_identity.credential_id)
        self.assertEqual(
            cached_peer["last_registry_srv_created"],
            transport.server_date,
        )
        self.assertEqual(
            cached_peer["last_registry_srv_modified"],
            transport.server_date + 1,
        )

    def test_shadow_trust_store_quarantines_mismatched_v1_self_scope(self):
        authority_a = realm_id_for_nightscout("https://authority-a.example.invalid")
        authority_b = realm_id_for_nightscout("https://authority-b.example.invalid")
        cases = [
            ("authority", authority_b, self.rig_identity),
            ("identity", authority_a, self.phone_identity),
        ]
        for label, configured_authority, identity in cases:
            with self.subTest(case=label):
                path = os.path.join(self.tmp, "mismatched-self-%s.json" % label)
                with open(path, "w") as handle:
                    json.dump({
                        "schema": "openaps.auth-shadow-state.v1",
                        "peers": {},
                        "self": self._legacy_self_state(authority_a),
                    }, handle)
                store = self._scoped_trust_store(
                    path,
                    configured_authority,
                    identity=identity,
                    device_kind="rig",
                )
                self.assertEqual(store.self_state(), {})
                quarantine = store.quarantine_state()
                self.assertEqual(len(quarantine["self"]), 1)
                with open(path, "r") as handle:
                    persisted = json.load(handle)
                self.assertFalse(persisted["self"])

    def test_shadow_trust_store_quarantines_malformed_and_colliding_v1_peers(self):
        authority = realm_id_for_nightscout("https://authority-a.example.invalid")
        valid = self._persisted_peer_record(authority)
        canonical_key = authority + ":" + self.phone_identity.credential_id
        collision_path = os.path.join(self.tmp, "colliding-shadow-state.json")
        with open(collision_path, "w") as handle:
            json.dump({
                "schema": "openaps.auth-shadow-state.v1",
                "peers": {
                    self.phone_identity.credential_id: valid,
                    canonical_key: valid,
                },
                "self": {},
            }, handle)
        colliding = self._scoped_trust_store(collision_path, authority)
        self.assertIsNone(colliding.peer(self.phone_identity.credential_id))
        self.assertEqual(len(colliding.quarantine_state()["peers"]), 2)

        malformed_records = []
        missing_authority = dict(valid)
        missing_authority.pop("authority_context_id")
        malformed_records.append(missing_authority)
        bad_realm = dict(valid)
        bad_realm["realm_id"] = "invalid-realm"
        malformed_records.append(bad_realm)
        wrong_kind = dict(valid)
        wrong_kind["device_kind"] = "rig"
        malformed_records.append(wrong_kind)
        wrong_protocol = dict(valid)
        wrong_protocol["protocol_version"] = 2
        malformed_records.append(wrong_protocol)
        wrong_registry = dict(valid)
        wrong_registry["registry_identifier"] = registry_identifier(self.rig_identity.credential_id)
        malformed_records.append(wrong_registry)
        noncanonical_key = dict(valid)
        noncanonical_key["public_key_der"] = noncanonical_key["public_key_der"].rstrip("=")
        malformed_records.append(noncanonical_key)
        mismatched_key = dict(valid)
        mismatched_key["public_key_der"] = base64.b64encode(
            self.rig_identity.public_key_der
        ).decode("ascii")
        malformed_records.append(mismatched_key)

        for index, malformed in enumerate(malformed_records):
            with self.subTest(index=index):
                path = os.path.join(self.tmp, "malformed-shadow-state-%d.json" % index)
                with open(path, "w") as handle:
                    json.dump({
                        "schema": "openaps.auth-shadow-state.v1",
                        "peers": {self.phone_identity.credential_id: malformed},
                        "self": {},
                    }, handle)
                store = self._scoped_trust_store(path, authority)
                self.assertIsNone(store.peer(self.phone_identity.credential_id))
                self.assertEqual(len(store.quarantine_state()["peers"]), 1)

    def test_shadow_trust_store_keeps_two_authorities_independent(self):
        path = os.path.join(self.tmp, "two-authority-shadow-state.json")
        authority_a = realm_id_for_nightscout("https://authority-a.example.invalid")
        authority_b = realm_id_for_nightscout("https://authority-b.example.invalid")
        peer = {
            "credential_id": self.phone_identity.credential_id,
            "device_kind": "phone",
            "realm_id": authority_a,
            "registry_identifier": registry_identifier(self.phone_identity.credential_id),
            "public_key_der": self.phone_identity.public_key_der,
            "nightscout_subject": "subject-placeholder",
            "srv_created": 1,
            "srv_modified": 1,
        }
        store_a = self._scoped_trust_store(path, authority_a)
        store_a.record_peer_confirmation(peer, "one_live_non_authoritative")
        store_a.record_lookup(
            self.phone_identity.credential_id,
            "candidate_revoked",
            "zero_live_non_authoritative",
        )
        store_a.record_self({
            "classification": "present",
            "last_registry_srv_created": 1,
            "last_registry_srv_modified": 1,
            "capability": {
                "supported": True,
                "security_enabled": True,
                "read": True,
                "create": True,
            },
        })

        peer_b = dict(peer)
        peer_b["realm_id"] = authority_b
        store_b = self._scoped_trust_store(path, authority_b)
        store_b.record_peer_confirmation(peer_b, "one_live_non_authoritative")
        store_b.record_self({
            "classification": "unsupported",
            "capability": {
                "supported": True,
                "security_enabled": True,
                "read": True,
                "create": False,
            },
        })

        peer_a = store_a.peer(self.phone_identity.credential_id)
        peer_b = store_b.peer(self.phone_identity.credential_id)
        self.assertIsNotNone(peer_a["candidate_revocation"])
        self.assertIsNone(peer_b["candidate_revocation"])
        self.assertEqual(peer_a["realm_id"], authority_a)
        self.assertEqual(peer_b["realm_id"], authority_b)
        self.assertEqual(store_a.self_state()["classification"], "present")
        self.assertEqual(store_b.self_state()["classification"], "unsupported")
        with open(path, "r") as handle:
            persisted = json.load(handle)
        self.assertEqual(len(persisted["peers"]), 2)
        self.assertEqual(len(persisted["self"]), 2)

    def test_shadow_trust_store_merges_actual_cross_process_writers(self):
        path = os.path.join(self.tmp, "shared-shadow-state.json")
        peer = {
            "credential_id": self.phone_identity.credential_id,
            "device_kind": "phone",
            "realm_id": realm_id_for_nightscout("https://peer-alias.example.invalid"),
            "registry_identifier": registry_identifier(self.phone_identity.credential_id),
            "public_key_der": self.phone_identity.public_key_der,
            "nightscout_subject": "subject-placeholder",
            "srv_created": 1,
            "srv_modified": 1,
        }
        authority_context_id = realm_id_for_nightscout("https://configured.example.invalid")
        self_state = {
            "classification": "present",
            "authority_context_id": authority_context_id,
            "last_registry_srv_created": 1,
            "last_registry_srv_modified": 1,
            "capability": {"supported": True},
        }
        peer_ready = multiprocessing.Event()
        self_ready = multiprocessing.Event()
        start = multiprocessing.Event()
        peer_done = multiprocessing.Event()
        peer_process = multiprocessing.Process(
            target=_cross_process_record_peer,
            args=(
                path,
                peer,
                authority_context_id,
                self.rig_identity.directory,
                peer_ready,
                start,
                peer_done,
            ),
        )
        self_process = multiprocessing.Process(
            target=_cross_process_record_self,
            args=(
                path,
                self_state,
                authority_context_id,
                self.rig_identity.directory,
                self_ready,
                peer_done,
            ),
        )

        peer_process.start()
        self_process.start()
        self.assertTrue(peer_ready.wait(10))
        self.assertTrue(self_ready.wait(10))
        start.set()
        peer_process.join(10)
        self_process.join(10)

        if peer_process.is_alive():
            peer_process.terminate()
            peer_process.join(5)
        if self_process.is_alive():
            self_process.terminate()
            self_process.join(5)
        self.assertEqual(peer_process.exitcode, 0)
        self.assertEqual(self_process.exitcode, 0)

        reloaded = self._scoped_trust_store(path, authority_context_id)
        self.assertIsNotNone(reloaded.peer(self.phone_identity.credential_id))
        self.assertEqual(reloaded.self_state()["classification"], "present")


if __name__ == "__main__":
    unittest.main()
