"""Authenticated proof I/O primitives, not enrollment or a background worker.

No installed runtime constructs this client yet. Its owner must supply bounded
jobs, cancellation, single-use pending challenges, protected-ingress evidence
and persistence. A successful read is not permission to promote trust.
"""
import json
import threading
import math
import uuid
from collections import namedtuple

from .authorization_protocol import proof_authority_context_id
from .nightscout_authorization import TemporaryJWTProvider, NightscoutAuthorizationError
from .write_challenge import (ChallengeError, validate_challenge, signed_response,
    response_identifier, response_envelope, decode_response_envelope, verify_response_signature, PendingChallenges)
from .authorization_tls import boottime
from .proof_http_transport import BoundedProofTransport

# Fresh key possession only, explicitly not an admission or persisted trust record.
FreshReadback = namedtuple("FreshReadback",
    "challenge response public_key_der issued_at verified_at owner_generation")
PermissionObservation = namedtuple("PermissionObservation",
    "outcome authority_context_id owner_generation started_at finished_at identifier")


def _permission_granted(data):
    """Bounded duplicate-aware Boolean control, never infer from truthiness."""
    if not isinstance(data, bytes) or not 0 < len(data) <= 8192:
        return None
    depth, quoted, escaped = 0, False, False
    for byte in data:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 4:
                return None
        elif byte in (93, 125):
            depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate permission field")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite permission field")
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        return obj["check"] if isinstance(obj, dict) and type(obj.get("check")) is bool else None
    except (ValueError, UnicodeError, RecursionError):
        return None


class NightscoutWriteProofClient:
    def __init__(self, base_url, identity, device_kind, access_token=None, api_secret=None,
                 clock=boottime, transport=None, anonymous_transport=None,
                 allow_insecure_http=False):
        # Validate even when a synthetic transport is supplied. Production uses
        # a dedicated verified-HTTPS, no-redirect transport with an 8-KiB cap.
        strict = BoundedProofTransport(base_url, clock=clock, allow_insecure_http=allow_insecure_http)
        if device_kind not in ("phone", "rig") or bool(access_token) == bool(api_secret):
            raise ChallengeError("one credential mode and valid role required")
        self._transport = transport if transport is not None else strict
        self._anonymous = anonymous_transport if anonymous_transport is not None else BoundedProofTransport(
            base_url, clock=clock, allow_insecure_http=allow_insecure_http)
        self._authority = proof_authority_context_id(base_url, allow_insecure_http=allow_insecure_http)
        self._identity, self._kind = identity, device_kind
        self._credential = identity.credential_id
        self._secret = api_secret
        self._clock = clock
        self._jwt = TemporaryJWTProvider(self._transport, access_token, monotonic=clock) if access_token else None
        self._operation = threading.Lock()
        self._invalidated = threading.Event()
        self._last = None
        self._rate_updated = None
        self._tokens = 6.0
        self._publications = {}
        self._pending = PendingChallenges(self._authority, self._credential, device_kind, clock=clock)
        self._owner_generation = uuid.uuid4()

    authority_context_id = property(lambda self: self._authority)

    def invalidate(self):
        # Does not block on I/O. The default transport observes cancellation
        # within its polling interval, kills/reaps the worker and rejects results.
        self._invalidated.set()
        self._pending.invalidate()
        for transport in (self._transport, self._anonymous):
            if isinstance(transport, BoundedProofTransport):
                transport.cancel()

    def issue_challenge(self, peer_credential_id, peer_kind):
        if not self._operation.acquire(False):
            raise ChallengeError("proof operation busy")
        try:
            self._check(self._clock())
            return self._pending.issue(peer_credential_id, peer_kind)
        finally:
            self._operation.release()

    def reap_cancelled_network_worker(self):
        """Lifecycle owner retains this client until cleanup returns True."""
        complete = True
        for transport in (self._transport, self._anonymous):
            if isinstance(transport, BoundedProofTransport):
                complete = transport.reap_cancelled_worker() and complete
        return complete

    def cancel_challenge(self, nonce):
        self._pending.cancel(nonce)

    def observe_enrollment_permissions(self):
        """Known-expression observations only, not the full ingress review."""
        if not self._operation.acquire(False):
            raise ChallengeError("proof client busy")
        try:
            started = self._begin()
            def result(outcome):
                finished = self._check(started)
                return PermissionObservation(outcome, self._authority, self._owner_generation, started, finished, uuid.uuid4())
            prefix = "/api/v2/authorization/debug/check/"
            status, data = self._request(started, "GET", prefix + "api:devicestatus:read")
            if status != 200 or _permission_granted(data) is not True:
                return result("inconclusive")
            inconclusive = False
            for permission in ("api:devicestatus:create", "api:*:create,update,delete"):
                self._check(started)
                # Never pass bearer, secret, body, cookies or query credentials.
                status, data = self._anonymous.request_bytes("GET", prefix + permission)
                self._check(started)
                if status == 401:
                    continue
                if status == 200 and _permission_granted(data) is True:
                    return result("public_write")
                inconclusive = True
            return result("inconclusive" if inconclusive else "denied_known_writes")
        finally:
            self._operation.release()

    def reviewed_policy_evidence(self, observation):
        """Mint opaque policy evidence from this live client's fresh observation."""
        self._validate_reviewed_policy_evidence(observation)
        from .reviewed_ingress_policy import _mint_live_client_evidence
        return _mint_live_client_evidence(self, observation)

    def _validate_reviewed_policy_evidence(self, observation):
        if not self._operation.acquire(False):
            raise ChallengeError("proof client busy")
        try:
            now = self._check(self._clock())
            if (not isinstance(observation, PermissionObservation) or
                    observation.owner_generation != self._owner_generation or
                    observation.authority_context_id != self._authority or
                    observation.outcome != "denied_known_writes" or
                    not math.isfinite(observation.started_at) or
                    not math.isfinite(observation.finished_at) or
                    not 0 <= observation.started_at <= observation.finished_at <= now or
                    observation.finished_at - observation.started_at >= 60 or
                    now - observation.finished_at >= 120):
                raise ChallengeError("reviewed-policy observation unavailable")
            return self._authority
        finally:
            self._operation.release()

    def read_fresh_peer_response(self, nonce, public_key_der):
        """Join independent readback to a single-use locally issued nonce.

        Absence permits bounded polling; errors cancel and success consumes.
        Protected-ingress evidence and admission policy are still mandatory.
        """
        if not self._operation.acquire(False):
            raise ChallengeError("proof client busy")
        try:
            fields = self._pending.pending_for_readback(nonce)
            try:
                response = self._read_peer_response_locked(fields, public_key_der)
                if response is None:
                    self._pending.pending_for_readback(nonce)
                    return None
                consumed = self._pending.consume_with_interval(nonce)
                if consumed.challenge != fields or self._invalidated.is_set():
                    raise ChallengeError("readback context invalidated")
                if self._last is not None and consumed.consumed_at < self._last:
                    self._invalidated.set()
                verified_at = self._check(consumed.consumed_at)
                if verified_at - consumed.issued_at >= 120:
                    raise ChallengeError("readback interval expired")
                # Clock values are scoped to this owner, not restartable expiry.
                return FreshReadback(consumed.challenge, response, public_key_der,
                    consumed.issued_at, verified_at, self._owner_generation)
            except Exception:
                self._pending.cancel(nonce)
                raise
        finally:
            self._operation.release()

    def validate_current_readback(self, receipt):
        """Local owner/lifetime recheck only, not admission or provenance.

        Accept only a locally returned FreshReadback, never deserialized input.
        Runtime settings/key checks remain mandatory around persistence. This
        method does not make a later commit atomic with invalidation.
        """
        if not self._operation.acquire(False):
            raise ChallengeError("proof client busy")
        try:
            self._validate_current_readback_locked(receipt)
        finally:
            self._operation.release()

    def _validate_current_readback_locked(self, receipt):
        if not isinstance(receipt, FreshReadback) or receipt.owner_generation != self._owner_generation:
            raise ChallengeError("readback owner mismatch")
        self._context(receipt.challenge, "verifier")
        now = self._check(self._clock())
        if not (receipt.issued_at <= receipt.verified_at <= now and now - receipt.issued_at < 120):
            raise ChallengeError("readback interval expired")

    def validate_observed_readback(self, receipt, before, after):
        """Join local observations/proof, not admission or policy attestation.

        Full ingress review and the approved stable-policy assumption remain
        mandatory. Never accept these local objects from external input.
        """
        if not self._operation.acquire(False):
            raise ChallengeError("proof client busy")
        try:
            self._validate_current_readback_locked(receipt)
            now = self._check(self._clock())
            for observation in (before, after):
                if (not isinstance(observation, PermissionObservation) or
                        observation.owner_generation != self._owner_generation or
                        observation.authority_context_id != self._authority or
                        observation.outcome != "denied_known_writes" or
                        not math.isfinite(observation.started_at) or not math.isfinite(observation.finished_at) or
                        not 0 <= observation.started_at <= observation.finished_at <= now or
                        observation.finished_at - observation.started_at >= 60):
                    raise ChallengeError("observation context")
            if (before.identifier == after.identifier or before.finished_at > receipt.issued_at or
                    after.started_at < receipt.verified_at or now - before.started_at >= 120):
                raise ChallengeError("observation order or workflow expiry")
        finally:
            self._operation.release()

    def _check(self, started):
        now = self._clock()
        if (not math.isfinite(now) or now < started or
                (self._last is not None and now < self._last) or
                self._identity.credential_id != self._credential):
            self.invalidate()
        self._last = now
        if self._invalidated.is_set() or not started <= now < started + 60:
            raise ChallengeError("proof operation expired or invalidated")
        return now

    def _begin(self):
        # Called with the operation lock held; reads and publications share one
        # six-attempt bucket, refilling one attempt per ten boottime seconds.
        now = self._clock()
        self._check(now)
        if self._rate_updated is not None:
            self._tokens = min(6.0, self._tokens + (now - self._rate_updated) / 10.0)
        self._rate_updated = now
        self._publications = {nonce: entry for nonce, entry in self._publications.items()
                              if now - entry[0] < 180}
        if self._tokens < 1:
            raise ChallengeError("proof operation rate limit")
        self._tokens -= 1
        return now

    def _request(self, started, method, path, body=None, query=None):
        self._check(started)
        headers = {"api_secret": self._secret} if self._secret else {"bearer": self._jwt.get_lease().token}
        self._check(started)
        status, raw = self._transport.request_bytes(method, path, body=body, query=query, **headers)
        self._check(started)
        # No automatic replay, including after ambiguous writes or 401s.
        if status == 401 and self._jwt:
            self._jwt.invalidate()
        return status, raw

    def _context(self, challenge, participant):
        fields = validate_challenge(challenge)
        if (fields["authority_context_id"] != self._authority or
                fields[participant + "_credential_id"] != self._credential or
                fields[participant + "_device_kind"] != self._kind):
            raise ChallengeError("proof participant context mismatch")
        return fields

    def publish_own_response(self, challenge):
        """Sign only this client's key as responder. Never publish supplied proof.

        One publication attempt, no automatic retry or issuer enrollment.
        A bounded in-memory intent prevents repeated writes for 180 seconds;
        this is not durable deduplication across owner/process replacement.
        """
        fields = self._context(challenge, "peer")
        if not self._operation.acquire(False):
            raise ChallengeError("proof client busy")
        try:
            started = self._begin()
            nonce = fields["nonce"]
            prior = self._publications.get(nonce)
            if prior is not None:
                if prior[1] != fields or not prior[2]:
                    raise ChallengeError("publication already attempted or nonce reused")
                return response_identifier(fields)
            if len(self._publications) >= 24:
                raise ChallengeError("publication intent capacity")
            # Record before signing or any I/O. Failed/ambiguous writes do not
            # become retriable by calling this method with the same challenge.
            self._publications[nonce] = (started, dict(fields), False)
            response = signed_response(fields, self._identity, self._authority, self._kind)
            path = "/api/v1/status.json" if self._secret else "/api/v3/status"
            status, raw = self._request(started, "GET", path)
            if status != 200:
                raise NightscoutAuthorizationError("proof_status", status=status)
            try:
                payload = json.loads(raw.decode("utf-8"))
                result = payload.get("result", payload)
                date = result.get("serverTimeEpoch" if self._secret else "srvDate")
            except (ValueError, AttributeError, UnicodeError):
                raise ChallengeError("invalid proof server date") from None
            body = json.loads(response_envelope(fields, response, date).decode("utf-8"))
            method = "POST" if self._secret else "PUT"
            path = "/api/v1/devicestatus/" if self._secret else "/api/v3/devicestatus/" + response_identifier(fields)
            status, _ = self._request(started, method, path, body=body)
            if status not in (200, 201):
                raise NightscoutAuthorizationError("proof_publication", status=status)
            self._publications[nonce] = (started, dict(fields), True)
            # Deliberately no response payload for an issuer to re-publish.
            return response_identifier(fields)
        finally:
            self._operation.release()

    def read_peer_response(self, challenge, public_key_der):
        """Independent HTTPS exact lookup + signature, still NOT admission.

        Missing rows return None for the owner's bounded poll policy. All other
        errors fail closed. Caller must recheck freshness and ingress evidence.
        """
        fields = self._context(challenge, "verifier")
        if not self._operation.acquire(False):
            raise ChallengeError("proof client busy")
        try:
            return self._read_peer_response_locked(fields, public_key_der)
        finally:
            self._operation.release()

    def _read_peer_response_locked(self, fields, public_key_der):
        self._context(fields, "verifier")
        started = self._begin()
        path = "/api/v1/devicestatus.json" if self._secret else "/api/v3/devicestatus/" + response_identifier(fields)
        query = {"count": "2", "find[identifier]": response_identifier(fields)} if self._secret else None
        status, raw = self._request(started, "GET", path, query=query)
        if status == 404:
            return None
        if status != 200:
            raise NightscoutAuthorizationError("proof_readback", status=status)
        response = decode_response_envelope(raw, fields, legacy_list=bool(self._secret))
        self._check(started)
        if response is None:
            return None
        verify_response_signature(fields, response, public_key_der, self._identity)
        self._check(started)
        return response
