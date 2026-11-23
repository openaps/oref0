"""Write-challenge format/key possession, NOT NS enrollment admission.

Fresh pending state, protected ingress and independently authenticated NS
readback remain mandatory. Nothing here updates trust or publishes a record.
"""
import base64
import binascii
import os
import re
import tempfile
import math
import threading
import json
from collections import namedtuple

from .authorization_tls import boottime

from .device_identity import (IdentityError, credential_id_for_public_key,
    validate_public_key_der, validate_signature_der, _run_openssl)

SCHEMA = "openaps.ns-write-challenge.v1"
RESPONSE_SCHEMA = "openaps.ns-write-response.v1"
NAMES = {"schema", "authority_context_id", "verifier_credential_id", "verifier_device_kind",
         "peer_credential_id", "peer_device_kind", "nonce"}
ORDER = ("authority_context_id", "verifier_credential_id", "verifier_device_kind",
         "peer_credential_id", "peer_device_kind", "nonce")
MAX_ENVELOPE_BYTES = 8192
ENVELOPE_APP = "openaps-device-write-proof"
Consumption = namedtuple("Consumption", "challenge issued_at consumed_at")


class ChallengeError(Exception):
    pass


class PendingChallenges:
    """Freshness only, never admission. No state survives process restart.

    The owner must bound readback/crypto jobs separately and invalidate this
    ledger when its authority or signing identity changes.
    """
    def __init__(self, authority, verifier, verifier_kind, clock=boottime, nonce=None):
        self._context = (authority, verifier, verifier_kind)
        self._clock = clock
        self._nonce = nonce or (lambda: binascii.hexlify(os.urandom(32)).decode("ascii"))
        self._lock = threading.Lock()
        self._valid = True
        self._last = None
        self._tokens = 6.0
        self._pending = {}

    def _advance(self):
        if not self._valid:
            raise ChallengeError("invalidated ledger")
        now = self._clock()
        if not math.isfinite(now) or (self._last is not None and now < self._last):
            self._valid = False
            self._pending.clear()
            raise ChallengeError("invalidated clock")
        if self._last is not None:
            self._tokens = min(6.0, self._tokens + (now - self._last) / 10.0)
        self._last = now
        self._pending = {nonce: entry for nonce, entry in self._pending.items()
                         if now - entry[1] < 120.0}
        return now

    def issue(self, peer, peer_kind):
        with self._lock:
            now = self._advance()
            authority, verifier, verifier_kind = self._context
            fields = validate_challenge({"schema": SCHEMA, "authority_context_id": authority,
                "verifier_credential_id": verifier, "verifier_device_kind": verifier_kind,
                "peer_credential_id": peer, "peer_device_kind": peer_kind, "nonce": "0" * 64})
            for existing, issued in self._pending.values():
                if existing["peer_credential_id"] == peer:
                    return dict(existing)  # Never expose mutable ledger state.
            if len(self._pending) >= 4:
                raise ChallengeError("pending capacity")
            if self._tokens < 1.0:
                raise ChallengeError("challenge rate limit")
            self._tokens -= 1.0
            fields["nonce"] = self._nonce()
            fields = validate_challenge(fields)
            if fields["nonce"] in self._pending:
                raise ChallengeError("nonce collision")
            self._pending[fields["nonce"]] = (fields, now)
            return dict(fields)

    def take_for_signature_verification(self, nonce):
        """One verification attempt, even if signature/readback later fails."""
        return self.consume_with_interval(nonce).challenge

    def consume_with_interval(self, nonce):
        """Atomic process-local interval evidence, not persisted freshness."""
        with self._lock:
            now = self._advance()
            entry = self._pending.pop(nonce, None)
            if entry is None:
                raise ChallengeError("unknown or expired nonce")
            return Consumption(dict(entry[0]), entry[1], now)

    def cancel(self, nonce):
        with self._lock:
            self._pending.pop(nonce, None)

    def pending_for_readback(self, nonce):
        """Non-consuming poll lookup; never extends the original deadline."""
        with self._lock:
            self._advance()
            entry = self._pending.get(nonce)
            if entry is None:
                raise ChallengeError("unknown or expired nonce")
            return dict(entry[0])

    def invalidate(self):
        with self._lock:
            self._valid = False
            self._pending.clear()


def validate_challenge(fields):
    def hex64(value):
        return isinstance(value, str) and len(value) == 64 and re.match(r"^[0-9a-f]{64}$", value)
    if (not isinstance(fields, dict) or set(fields) != NAMES or
            not all(isinstance(value, str) for value in fields.values()) or fields["schema"] != SCHEMA or
            not fields["authority_context_id"].startswith("ns_") or not hex64(fields["authority_context_id"][3:]) or
            not all(hex64(fields[key]) for key in ("verifier_credential_id", "peer_credential_id", "nonce")) or
            fields["verifier_credential_id"] == fields["peer_credential_id"] or
            fields["verifier_device_kind"] not in ("phone", "rig") or fields["peer_device_kind"] not in ("phone", "rig") or
            fields["verifier_device_kind"] == fields["peer_device_kind"]):
        raise ChallengeError("invalid challenge shape")
    return dict(fields)


def fresh_challenge(authority, verifier, verifier_kind, peer, peer_kind):
    return validate_challenge({"schema": SCHEMA, "authority_context_id": authority,
        "verifier_credential_id": verifier, "verifier_device_kind": verifier_kind,
        "peer_credential_id": peer, "peer_device_kind": peer_kind,
        "nonce": binascii.hexlify(os.urandom(32)).decode("ascii")})


def signing_bytes(challenge):
    fields = validate_challenge(challenge)
    return ("\x00".join([RESPONSE_SCHEMA] + [fields[name] for name in ORDER])).encode("ascii")


def response_identifier(challenge):
    return "openaps-ns-write-response-" + validate_challenge(challenge)["nonce"]


def _response_shape(challenge, response):
    fields = validate_challenge(challenge)
    if (not isinstance(response, dict) or set(response) != NAMES | {"signature"} or
            response["schema"] != RESPONSE_SCHEMA or any(response[name] != fields[name] for name in ORDER) or
            not isinstance(response["signature"], str) or len(response["signature"]) > 104):
        raise ChallengeError("invalid response shape")
    try:
        signature = base64.b64decode(response["signature"], validate=True)
        if base64.b64encode(signature).decode("ascii") != response["signature"]:
            raise ChallengeError("noncanonical signature encoding")
        validate_signature_der(signature)
    except (IdentityError, ValueError, binascii.Error):
        raise ChallengeError("invalid response signature encoding") from None
    return dict(response)


def response_envelope(challenge, response, server_date_ms):
    """Encode a publication body, not authorization evidence or an HTTP action."""
    payload = _response_shape(challenge, response)
    if type(server_date_ms) is not int or not 0 < server_date_ms <= 9007199254740991:
        raise ChallengeError("invalid envelope date")
    record = {"app": ENVELOPE_APP, "identifier": response_identifier(challenge),
        "device": "openaps-auth://%s/%s" % (payload["peer_device_kind"], payload["peer_credential_id"]),
        "date": server_date_ms, "utcOffset": 0, "openaps_write_response": payload}
    data = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_ENVELOPE_BYTES:
        raise ChallengeError("oversized response envelope")
    return data


def decode_response_envelope(data, challenge, legacy_list=False):
    """Decode one v3 exact-lookup result; never infer freshness or NS provenance.

    Server metadata is ignored, not passed to signature validation. The network
    owner must bound bytes while reading, authenticate HTTPS and reject redirects.
    """
    validate_challenge(challenge)
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_ENVELOPE_BYTES:
        raise ChallengeError("invalid response envelope size")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ChallengeError("duplicate envelope key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ChallengeError("nonfinite JSON constant")
    try:
        # Bound nesting before the parser allocates nested containers.
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
                if depth > 8:
                    raise ChallengeError("envelope nesting limit")
            elif byte in (93, 125):
                depth -= 1
        outer = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)
        if legacy_list:
            if not isinstance(outer, list) or len(outer) > 1:
                raise ChallengeError("ambiguous legacy response lookup")
            if not outer:
                return None
            outer = outer[0]
        if not isinstance(outer, dict):
            raise ChallengeError("invalid envelope object")
        # Exact v3 lookup may wrap a single record in result, never a list.
        record = outer.get("result", outer)
        expected_device = "openaps-auth://%s/%s" % (challenge["peer_device_kind"], challenge["peer_credential_id"])
        if (not isinstance(record, dict) or record.get("app") != ENVELOPE_APP or
                record.get("identifier") != response_identifier(challenge) or record.get("device") != expected_device or
                type(record.get("date")) is not int or not 0 < record["date"] <= 9007199254740991 or
                type(record.get("utcOffset")) is not int or not -1440 <= record["utcOffset"] <= 1440):
            raise ChallengeError("invalid envelope binding")
        return _response_shape(challenge, record.get("openaps_write_response"))
    except (ValueError, UnicodeError, RecursionError):
        raise ChallengeError("malformed response envelope") from None


def signed_response(challenge, identity, authority, device_kind):
    fields = validate_challenge(challenge)
    if (fields["authority_context_id"] != authority or fields["peer_credential_id"] != identity.credential_id or
            fields["peer_device_kind"] != device_kind):
        raise ChallengeError("response context mismatch")
    fields["schema"] = RESPONSE_SCHEMA
    fields["signature"] = base64.b64encode(identity.sign(signing_bytes(challenge))).decode("ascii")
    return fields


def verify_response_signature(challenge, response, public_key_der, verifier_identity):
    fields = validate_challenge(challenge)
    # Fixed uncompressed P-256 SPKI, before hashing or starting OpenSSL.
    if not isinstance(public_key_der, bytes) or len(public_key_der) != 91:
        raise ChallengeError("invalid public key size")
    if (not isinstance(response, dict) or set(response) != NAMES | {"signature"} or
            response["schema"] != RESPONSE_SCHEMA or any(response[name] != fields[name] for name in ORDER) or
            credential_id_for_public_key(public_key_der) != fields["peer_credential_id"] or
            not isinstance(response["signature"], str) or len(response["signature"]) > 104):
        raise ChallengeError("invalid response shape")
    try:
        signature = base64.b64decode(response["signature"], validate=True)
        if base64.b64encode(signature).decode("ascii") != response["signature"]:
            raise ChallengeError("noncanonical signature encoding")
        validate_signature_der(signature)
        validate_public_key_der(public_key_der, verifier_identity.openssl_path, verifier_identity.openssl_lock_path)
        # Verify without putting an unproven key in the persistent peer cache.
        with tempfile.TemporaryDirectory(prefix="openaps-write-signature-") as directory:
            key_path, signature_path = os.path.join(directory, "key.der"), os.path.join(directory, "signature.der")
            for path, data in ((key_path, public_key_der), (signature_path, signature)):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
            _run_openssl([verifier_identity.openssl_path, "dgst", "-sha256", "-verify", key_path,
                "-keyform", "DER", "-signature", signature_path], input_bytes=signing_bytes(challenge),
                lock_path=verifier_identity.openssl_lock_path)
    except (IdentityError, ValueError, binascii.Error):
        raise ChallengeError("invalid response signature") from None
