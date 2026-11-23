from __future__ import print_function

import base64
import hashlib
import json
import math
import os
import re
import time
import uuid
try:
    from urllib.parse import urlparse, urlsplit, quote
except ImportError:
    from urlparse import urlparse, urlsplit
    from urllib import quote

from .device_identity import (
    SIGNING_ALGORITHM,
    credential_id_for_public_key,
    validate_public_key_der,
    validate_signature_der,
)


AUTHORIZATION_PROTOCOL_VERSION = 1
ENROLLMENT_SCHEMA = "openaps.ns-device-auth.v1"
AUTH_HELLO_SCHEMA = "openaps.ble.auth-hello.v1"
AUTH_ACK_SCHEMA = "openaps.ble.auth-ack.v1"
SIGNED_EVENT_SCHEMA = "openaps.ble.event.v2"
SIGNED_ACK_SCHEMA = "openaps.ble.event-ack.v2"
SHADOW_OBSERVATION_SCHEMA = "openaps.authorization-shadow-observation.v1"
REGISTRY_PREFIX = "openaps-auth-v1-"
LEGACY_V1_AUTHENTICATED_CARRIER = "nightscout-v1-api-secret"
CONTINUITY_STALE_SECONDS = 24 * 60 * 60
FUTURE_CLOCK_SKEW_SECONDS = 5 * 60
CHALLENGE_BYTES = 32
CHALLENGE_LIFETIME_SECONDS = 5 * 60
SESSION_IDLE_SECONDS = 5 * 60
SESSION_ABSOLUTE_SECONDS = 30 * 60
MAX_SESSIONS_PER_CREDENTIAL = 2
MAX_SESSIONS_GLOBAL = 8
BLE_AUTH_ATTEMPT_CAPACITY = 6
HTTP_AUTH_ATTEMPT_CAPACITY = 6
BLE_AUTH_ATTEMPT_REFILL_SECONDS = 10
HTTP_AUTH_ATTEMPT_REFILL_SECONDS = 10
BLE_UNKNOWN_CREDENTIAL_LIMIT = 5
HTTP_UNKNOWN_CREDENTIAL_LIMIT = 5
BLE_CREDENTIAL_ATTEMPT_CAPACITY = 2
HTTP_CREDENTIAL_ATTEMPT_CAPACITY = 1
BLE_CREDENTIAL_REFILL_SECONDS = 60
HTTP_CREDENTIAL_REFILL_SECONDS = 60
BLE_MAX_SESSIONS_PER_CREDENTIAL = 1
HTTP_MAX_SESSIONS_PER_CREDENTIAL = 1
BLE_MAX_SESSIONS_GLOBAL = 4
HTTP_MAX_SESSIONS_GLOBAL = 4
MAX_AUTH_MESSAGE_BYTES = 4 * 1024
MAX_EVENT_MESSAGE_BYTES = 64 * 1024
MAX_AUTH_CHUNKS = 32
MAX_EVENT_CHUNKS = 384

_CREDENTIAL_RE = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_RE = re.compile(r"^openaps-auth-v1-[0-9a-f]{64}$")
_REALM_RE = re.compile(r"^ns_[0-9a-f]{64}$")
_DEVICE_KINDS = set(["phone", "rig"])


class AuthorizationError(Exception):
    pass


def _positive_integral_timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(numeric) and value > 0 and numeric.is_integer()


def _as_text(value, field, maximum=256):
    if not isinstance(value, str):
        raise AuthorizationError("%s must be a string" % field)
    if not value or len(value) > maximum or "\n" in value or "\r" in value:
        raise AuthorizationError("%s is invalid" % field)
    return value


def _credential(value, field="credential_id"):
    value = _as_text(value, field, 64)
    if not _CREDENTIAL_RE.match(value):
        raise AuthorizationError("%s is invalid" % field)
    return value


def registry_identifier(credential_id):
    return REGISTRY_PREFIX + _credential(credential_id)


def _registry_identifier(value):
    value = _as_text(value, "registry_identifier", len(REGISTRY_PREFIX) + 64)
    if not _REGISTRY_RE.match(value):
        raise AuthorizationError("registry_identifier is invalid")
    return value


def _uuid(value, field):
    value = _as_text(value, field, 36)
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise AuthorizationError("%s is invalid" % field)
    canonical = str(parsed)
    if value.lower() != canonical:
        raise AuthorizationError("%s is not canonical" % field)
    return canonical


def _base64_decode(value, field, exact_bytes=None, maximum_bytes=1024):
    value = _as_text(value, field, ((maximum_bytes + 2) // 3) * 4 + 4)
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception:
        raise AuthorizationError("%s is invalid base64" % field)
    if len(decoded) > maximum_bytes:
        raise AuthorizationError("%s is too large" % field)
    if exact_bytes is not None and len(decoded) != exact_bytes:
        raise AuthorizationError("%s has invalid length" % field)
    canonical = base64.b64encode(decoded).decode("ascii")
    if canonical != value:
        raise AuthorizationError("%s is not canonical base64" % field)
    return decoded


def _base64_encode(value):
    return base64.b64encode(value).decode("ascii")


def _transcript(lines):
    normalized = []
    for index, line in enumerate(lines):
        normalized.append(_as_text(line, "transcript[%d]" % index, 2048))
    return "\n".join(normalized).encode("utf-8")


def canonical_origin(nightscout_url):
    value = _as_text(nightscout_url, "nightscout_url", 2048).strip()
    parsed = urlparse(value if "://" in value else "https://" + value)
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    if scheme not in ("http", "https") or not host:
        raise AuthorizationError("Nightscout origin is invalid")
    try:
        port = parsed.port
    except ValueError:
        raise AuthorizationError("Nightscout port is invalid")
    include_port = port is not None and not (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    )
    return "%s://%s%s" % (scheme, host, ":%d" % port if include_port else "")


def realm_id_for_nightscout(nightscout_url):
    digest = hashlib.sha256(canonical_origin(nightscout_url).encode("utf-8")).hexdigest()
    return "ns_" + digest.lower()


def proof_authority_context_id(nightscout_url, allow_insecure_http=False):
    """Path-aware new proof/cache scope; legacy realm labels stay unchanged."""
    parsed = urlsplit(nightscout_url)
    if (parsed.scheme not in (("https", "http") if allow_insecure_http else ("https",)) or
            not parsed.hostname or parsed.username is not None or
            parsed.password is not None or parsed.query or parsed.fragment):
        raise AuthorizationError("invalid proof authority")
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    else:
        host = host.encode("idna").decode("ascii")
    try:
        port = parsed.port
    except ValueError:
        raise AuthorizationError("invalid proof port")
    default_port = 443 if parsed.scheme == "https" else 80
    origin = parsed.scheme + "://" + host + (":" + str(port) if port is not None and port != default_port else "")
    path = quote(parsed.path, safe="/%:@!$&'()*+,;=-._~").rstrip("/")
    payload = "openaps.ns-proof-authority.v2\x00" + origin + "\x00" + path
    return "ns_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def enrollment_transcript(
    identifier,
    credential_id,
    device_kind,
    public_key_base64,
    record_sequence,
    record_nonce_base64,
):
    identifier = _registry_identifier(identifier)
    credential_id = _credential(credential_id)
    if device_kind not in _DEVICE_KINDS:
        raise AuthorizationError("device_kind is invalid")
    _base64_decode(public_key_base64, "signing_public_key", maximum_bytes=512)
    if not isinstance(record_sequence, int) or isinstance(record_sequence, bool) or record_sequence < 1:
        raise AuthorizationError("record_sequence is invalid")
    _base64_decode(record_nonce_base64, "record_nonce", exact_bytes=32, maximum_bytes=32)
    return _transcript([
        ENROLLMENT_SCHEMA,
        identifier,
        credential_id,
        device_kind,
        SIGNING_ALGORITHM,
        public_key_base64,
        str(record_sequence),
        record_nonce_base64,
    ])


def build_enrollment_record(
    identity,
    device_kind,
    nightscout_url,
    server_date_millis,
    nonce=None,
    authorization_carrier=None,
):
    if device_kind not in _DEVICE_KINDS:
        raise AuthorizationError("device_kind is invalid")
    if not isinstance(server_date_millis, int) or isinstance(server_date_millis, bool) or server_date_millis < 1:
        raise AuthorizationError("server_date_millis is invalid")
    nonce = nonce if nonce is not None else os.urandom(32)
    if not isinstance(nonce, bytes) or len(nonce) != 32:
        raise AuthorizationError("record nonce is invalid")
    credential_id = _credential(identity.credential_id)
    identifier = registry_identifier(credential_id)
    public_key_base64 = _base64_encode(identity.public_key_der)
    nonce_base64 = _base64_encode(nonce)
    transcript = enrollment_transcript(
        identifier,
        credential_id,
        device_kind,
        public_key_base64,
        1,
        nonce_base64,
    )
    proof = _base64_encode(identity.sign(transcript))
    record = {
        "app": "openaps-device-authorization",
        "device": "openaps-auth://%s/%s" % (device_kind, credential_id),
        "date": server_date_millis,
        "utcOffset": 0,
        "openaps_auth": {
            "schema": ENROLLMENT_SCHEMA,
            "realm_id": realm_id_for_nightscout(nightscout_url),
            "credential_id": credential_id,
            "device_kind": device_kind,
            "signing_algorithm": SIGNING_ALGORITHM,
            "signing_public_key": public_key_base64,
            "record_sequence": 1,
            "record_nonce": nonce_base64,
            "proof": proof,
        },
    }
    if authorization_carrier is not None:
        if authorization_carrier != LEGACY_V1_AUTHENTICATED_CARRIER:
            raise AuthorizationError("authorization carrier is invalid")
        record["openaps_auth_carrier"] = authorization_carrier
    return record


def validate_enrollment_document(document, expected_credential_id, expected_device_kind, identity):
    if not isinstance(document, dict):
        raise AuthorizationError("enrollment document must be an object")
    srv_created = document.get("srvCreated")
    srv_modified = document.get("srvModified")
    if not _positive_integral_timestamp(srv_created):
        raise AuthorizationError("enrollment srvCreated is invalid")
    if not _positive_integral_timestamp(srv_modified):
        raise AuthorizationError("enrollment srvModified is invalid")
    identifier = _registry_identifier(document.get("identifier"))
    expected_credential_id = _credential(expected_credential_id)
    if identifier != registry_identifier(expected_credential_id):
        raise AuthorizationError("enrollment identifier mismatch")
    if document.get("app") != "openaps-device-authorization":
        raise AuthorizationError("enrollment app is invalid")
    if not _positive_integral_timestamp(document.get("date")):
        raise AuthorizationError("enrollment date is invalid")
    if document.get("utcOffset") != 0:
        raise AuthorizationError("enrollment utcOffset is invalid")
    auth = document.get("openaps_auth")
    if not isinstance(auth, dict):
        raise AuthorizationError("openaps_auth is missing")
    required = set([
        "schema", "realm_id", "credential_id", "device_kind",
        "signing_algorithm", "signing_public_key", "record_sequence",
        "record_nonce", "proof",
    ])
    if set(auth.keys()) != required:
        raise AuthorizationError("openaps_auth fields are invalid")
    if auth.get("schema") != ENROLLMENT_SCHEMA:
        raise AuthorizationError("enrollment schema is invalid")
    if not _REALM_RE.match(_as_text(auth.get("realm_id"), "realm_id", 67)):
        raise AuthorizationError("realm_id is invalid")
    credential_id = _credential(auth.get("credential_id"))
    if credential_id != expected_credential_id:
        raise AuthorizationError("enrollment credential mismatch")
    device_kind = auth.get("device_kind")
    if device_kind != expected_device_kind or device_kind not in _DEVICE_KINDS:
        raise AuthorizationError("enrollment device kind mismatch")
    if auth.get("signing_algorithm") != SIGNING_ALGORITHM:
        raise AuthorizationError("signing algorithm is invalid")
    public_key_der = _base64_decode(auth.get("signing_public_key"), "signing_public_key", maximum_bytes=512)
    validate_public_key_der(public_key_der, identity.openssl_path, identity.openssl_lock_path)
    if credential_id_for_public_key(public_key_der) != credential_id:
        raise AuthorizationError("public key credential mismatch")
    record_sequence = auth.get("record_sequence")
    transcript = enrollment_transcript(
        identifier,
        credential_id,
        device_kind,
        auth.get("signing_public_key"),
        record_sequence,
        auth.get("record_nonce"),
    )
    signature_der = _base64_decode(auth.get("proof"), "proof", maximum_bytes=80)
    validate_signature_der(signature_der)
    if not identity.verify(transcript, signature_der, credential_id, public_key_der):
        raise AuthorizationError("enrollment proof is invalid")
    expected_device = "openaps-auth://%s/%s" % (device_kind, credential_id)
    if document.get("device") != expected_device:
        raise AuthorizationError("enrollment device is invalid")
    subject = document.get("subject")
    if subject is not None and (not isinstance(subject, str) or not subject or len(subject) > 256):
        raise AuthorizationError("server-stamped subject is invalid")
    authorization_carrier = document.get("openaps_auth_carrier")
    if authorization_carrier is not None and authorization_carrier != LEGACY_V1_AUTHENTICATED_CARRIER:
        raise AuthorizationError("authorization carrier is invalid")
    return {
        "credential_id": credential_id,
        "public_key_der": public_key_der,
        "device_kind": device_kind,
        "realm_id": auth.get("realm_id"),
        "registry_identifier": identifier,
        "nightscout_subject": subject,
        "authorization_carrier": authorization_carrier,
        "srv_created": srv_created,
        "srv_modified": srv_modified,
    }


def auth_hello_transcript(message):
    if not isinstance(message, dict) or message.get("schema") != AUTH_HELLO_SCHEMA:
        raise AuthorizationError("auth hello schema is invalid")
    allowed = set([
        "schema", "authorization_protocol_version", "message_id",
        "phone_credential_id", "rig_credential_id", "rig_challenge",
        "phone_challenge", "signature",
    ])
    if set(message.keys()) not in (allowed, allowed - set(["signature"])):
        raise AuthorizationError("auth hello fields are invalid")
    if message.get("authorization_protocol_version") != AUTHORIZATION_PROTOCOL_VERSION:
        raise AuthorizationError("auth hello version is invalid")
    return _transcript([
        AUTH_HELLO_SCHEMA,
        str(AUTHORIZATION_PROTOCOL_VERSION),
        _uuid(message.get("message_id"), "message_id"),
        _credential(message.get("phone_credential_id"), "phone_credential_id"),
        _credential(message.get("rig_credential_id"), "rig_credential_id"),
        _canonical_challenge(message.get("rig_challenge"), "rig_challenge"),
        _canonical_challenge(message.get("phone_challenge"), "phone_challenge"),
    ])


def validate_auth_hello_shape(message):
    """Validate every cheap auth-hello field before network or OpenSSL work."""
    if not isinstance(message, dict):
        raise AuthorizationError("auth hello must be an object")
    allowed = set([
        "schema", "authorization_protocol_version", "message_id",
        "phone_credential_id", "rig_credential_id", "rig_challenge",
        "phone_challenge", "signature",
    ])
    if set(message.keys()) != allowed:
        raise AuthorizationError("auth hello fields are invalid")
    auth_hello_transcript(message)
    signature = _base64_decode(message.get("signature"), "signature", maximum_bytes=80)
    validate_signature_der(signature)
    return message


def _canonical_challenge(value, field):
    _base64_decode(value, field, exact_bytes=CHALLENGE_BYTES, maximum_bytes=CHALLENGE_BYTES)
    return value


def build_auth_hello(identity, rig_credential_id, rig_challenge, phone_challenge=None, message_id=None):
    message = {
        "schema": AUTH_HELLO_SCHEMA,
        "authorization_protocol_version": AUTHORIZATION_PROTOCOL_VERSION,
        "message_id": str(uuid.UUID(message_id)) if message_id else str(uuid.uuid4()),
        "phone_credential_id": identity.credential_id,
        "rig_credential_id": _credential(rig_credential_id, "rig_credential_id"),
        "rig_challenge": _canonical_challenge(rig_challenge, "rig_challenge"),
        "phone_challenge": _base64_encode(phone_challenge if phone_challenge is not None else os.urandom(32)),
    }
    message["signature"] = _base64_encode(identity.sign(auth_hello_transcript(message)))
    return message


def verify_auth_hello(message, expected_rig_credential_id, phone_public_key_der, identity):
    validate_auth_hello_shape(message)
    if message.get("rig_credential_id") != expected_rig_credential_id:
        raise AuthorizationError("auth hello destination mismatch")
    phone_credential_id = _credential(message.get("phone_credential_id"), "phone_credential_id")
    if credential_id_for_public_key(phone_public_key_der) != phone_credential_id:
        raise AuthorizationError("auth hello public key mismatch")
    signature = _base64_decode(message.get("signature"), "signature", maximum_bytes=80)
    if not identity.verify(auth_hello_transcript(message), signature, phone_credential_id, phone_public_key_der):
        raise AuthorizationError("auth hello signature is invalid")
    return message


def auth_ack_transcript(message):
    if not isinstance(message, dict) or message.get("schema") != AUTH_ACK_SCHEMA:
        raise AuthorizationError("auth ack schema is invalid")
    allowed = set([
        "schema", "authorization_protocol_version", "message_id", "session_id",
        "phone_credential_id", "rig_credential_id", "rig_challenge",
        "phone_challenge", "signature",
    ])
    if set(message.keys()) not in (allowed, allowed - set(["signature"])):
        raise AuthorizationError("auth ack fields are invalid")
    if message.get("authorization_protocol_version") != AUTHORIZATION_PROTOCOL_VERSION:
        raise AuthorizationError("auth ack version is invalid")
    return _transcript([
        AUTH_ACK_SCHEMA,
        str(AUTHORIZATION_PROTOCOL_VERSION),
        _uuid(message.get("message_id"), "message_id"),
        _uuid(message.get("session_id"), "session_id"),
        _credential(message.get("phone_credential_id"), "phone_credential_id"),
        _credential(message.get("rig_credential_id"), "rig_credential_id"),
        _canonical_challenge(message.get("rig_challenge"), "rig_challenge"),
        _canonical_challenge(message.get("phone_challenge"), "phone_challenge"),
    ])


def build_auth_ack(identity, hello, session_id=None):
    message = {
        "schema": AUTH_ACK_SCHEMA,
        "authorization_protocol_version": AUTHORIZATION_PROTOCOL_VERSION,
        "message_id": _uuid(hello.get("message_id"), "message_id"),
        "session_id": str(uuid.UUID(session_id)) if session_id else str(uuid.uuid4()),
        "phone_credential_id": _credential(hello.get("phone_credential_id"), "phone_credential_id"),
        "rig_credential_id": identity.credential_id,
        "rig_challenge": _canonical_challenge(hello.get("rig_challenge"), "rig_challenge"),
        "phone_challenge": _canonical_challenge(hello.get("phone_challenge"), "phone_challenge"),
    }
    message["signature"] = _base64_encode(identity.sign(auth_ack_transcript(message)))
    return message


def verify_auth_ack(message, expected_hello, rig_public_key_der, identity):
    if not isinstance(message, dict):
        raise AuthorizationError("auth ack must be an object")
    allowed = set([
        "schema", "authorization_protocol_version", "message_id", "session_id",
        "phone_credential_id", "rig_credential_id", "rig_challenge",
        "phone_challenge", "signature",
    ])
    if set(message.keys()) != allowed:
        raise AuthorizationError("auth ack fields are invalid")
    for field in ("message_id", "phone_credential_id", "rig_credential_id", "rig_challenge", "phone_challenge"):
        if message.get(field) != expected_hello.get(field):
            raise AuthorizationError("auth ack %s mismatch" % field)
    rig_credential_id = _credential(message.get("rig_credential_id"), "rig_credential_id")
    if credential_id_for_public_key(rig_public_key_der) != rig_credential_id:
        raise AuthorizationError("auth ack public key mismatch")
    signature = _base64_decode(message.get("signature"), "signature", maximum_bytes=80)
    validate_signature_der(signature)
    if not identity.verify(auth_ack_transcript(message), signature, rig_credential_id, rig_public_key_der):
        raise AuthorizationError("auth ack signature is invalid")
    return message


def event_transcript(message):
    if not isinstance(message, dict) or message.get("schema") != SIGNED_EVENT_SCHEMA:
        raise AuthorizationError("signed event schema is invalid")
    if message.get("authorization_protocol_version") != AUTHORIZATION_PROTOCOL_VERSION:
        raise AuthorizationError("signed event version is invalid")
    payload = _base64_decode(message.get("payload"), "payload", maximum_bytes=MAX_EVENT_MESSAGE_BYTES)
    digest = hashlib.sha256(payload).hexdigest()
    if message.get("payload_sha256") != digest:
        raise AuthorizationError("signed event payload digest mismatch")
    legacy_ack_digest = _as_text(
        message.get("legacy_ack_sha256"),
        "legacy_ack_sha256",
        64,
    )
    if not re.match(r"^[0-9a-f]{64}$", legacy_ack_digest):
        raise AuthorizationError("signed event legacy ack digest is invalid")
    return _transcript([
        SIGNED_EVENT_SCHEMA,
        str(AUTHORIZATION_PROTOCOL_VERSION),
        _uuid(message.get("session_id"), "session_id"),
        _credential(message.get("sender_credential_id"), "sender_credential_id"),
        _credential(message.get("destination_credential_id"), "destination_credential_id"),
        _as_text(message.get("message_id"), "message_id", 128),
        _canonical_challenge(message.get("message_nonce"), "message_nonce"),
        digest,
        legacy_ack_digest,
    ])


def build_signed_event(
    identity,
    session_id,
    destination_credential_id,
    message_id,
    payload_bytes,
    legacy_ack_bytes,
    nonce=None,
):
    if (
        not isinstance(payload_bytes, bytes) or
        len(payload_bytes) > MAX_EVENT_MESSAGE_BYTES or
        not isinstance(legacy_ack_bytes, bytes) or
        not legacy_ack_bytes or
        len(legacy_ack_bytes) > MAX_EVENT_MESSAGE_BYTES
    ):
        raise AuthorizationError("event payload is invalid")
    nonce = nonce if nonce is not None else os.urandom(32)
    message = {
        "schema": SIGNED_EVENT_SCHEMA,
        "authorization_protocol_version": AUTHORIZATION_PROTOCOL_VERSION,
        "session_id": _uuid(session_id, "session_id"),
        "sender_credential_id": identity.credential_id,
        "destination_credential_id": _credential(destination_credential_id, "destination_credential_id"),
        "message_id": _as_text(message_id, "message_id", 128),
        "message_nonce": _base64_encode(nonce),
        "payload": _base64_encode(payload_bytes),
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "legacy_ack_sha256": hashlib.sha256(legacy_ack_bytes).hexdigest(),
    }
    message["signature"] = _base64_encode(identity.sign(event_transcript(message)))
    return message


def validate_signed_event(message, public_key_der, identity):
    allowed = set([
        "schema", "authorization_protocol_version", "session_id",
        "sender_credential_id", "destination_credential_id", "message_id",
        "message_nonce", "payload", "payload_sha256", "legacy_ack_sha256",
        "signature",
    ])
    if not isinstance(message, dict) or set(message.keys()) != allowed:
        raise AuthorizationError("signed event fields are invalid")
    sender = _credential(message.get("sender_credential_id"), "sender_credential_id")
    if credential_id_for_public_key(public_key_der) != sender:
        raise AuthorizationError("signed event public key mismatch")
    signature = _base64_decode(message.get("signature"), "signature", maximum_bytes=80)
    validate_signature_der(signature)
    if not identity.verify(event_transcript(message), signature, sender, public_key_der):
        raise AuthorizationError("signed event signature is invalid")
    return _base64_decode(message.get("payload"), "payload", maximum_bytes=MAX_EVENT_MESSAGE_BYTES)


def ack_transcript(message):
    if not isinstance(message, dict) or message.get("schema") != SIGNED_ACK_SCHEMA:
        raise AuthorizationError("signed ack schema is invalid")
    if message.get("authorization_protocol_version") != AUTHORIZATION_PROTOCOL_VERSION:
        raise AuthorizationError("signed ack version is invalid")
    payload = _base64_decode(message.get("payload"), "payload", maximum_bytes=MAX_EVENT_MESSAGE_BYTES)
    digest = hashlib.sha256(payload).hexdigest()
    if message.get("payload_sha256") != digest:
        raise AuthorizationError("signed ack payload digest mismatch")
    return _transcript([
        SIGNED_ACK_SCHEMA,
        str(AUTHORIZATION_PROTOCOL_VERSION),
        _uuid(message.get("session_id"), "session_id"),
        _credential(message.get("sender_credential_id"), "sender_credential_id"),
        _credential(message.get("destination_credential_id"), "destination_credential_id"),
        _as_text(message.get("event_id"), "event_id", 128),
        _canonical_challenge(message.get("request_nonce"), "request_nonce"),
        digest,
    ])


def build_signed_ack(identity, session_id, destination_credential_id, event_id, request_nonce, payload_bytes):
    if not isinstance(payload_bytes, bytes) or len(payload_bytes) > MAX_EVENT_MESSAGE_BYTES:
        raise AuthorizationError("ack payload is invalid")
    message = {
        "schema": SIGNED_ACK_SCHEMA,
        "authorization_protocol_version": AUTHORIZATION_PROTOCOL_VERSION,
        "session_id": _uuid(session_id, "session_id"),
        "sender_credential_id": identity.credential_id,
        "destination_credential_id": _credential(destination_credential_id, "destination_credential_id"),
        "request_nonce": _canonical_challenge(request_nonce, "request_nonce"),
        "event_id": _as_text(event_id, "event_id", 128),
        "payload": _base64_encode(payload_bytes),
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }
    message["signature"] = _base64_encode(identity.sign(ack_transcript(message)))
    return message


def build_shadow_observation(event, signed_event, legacy_ack_bytes):
    if (
        not isinstance(event, dict) or
        not isinstance(signed_event, dict) or
        not isinstance(legacy_ack_bytes, bytes) or
        not legacy_ack_bytes or
        len(legacy_ack_bytes) > MAX_EVENT_MESSAGE_BYTES
    ):
        raise AuthorizationError("shadow observation input is invalid")
    event_id = _as_text(event.get("event_id"), "event_id", 128)
    if event_id != _as_text(signed_event.get("message_id"), "message_id", 128):
        raise AuthorizationError("shadow observation event mismatch")
    payload_sha256 = _as_text(signed_event.get("payload_sha256"), "payload_sha256", 64)
    if not re.match(r"^[0-9a-f]{64}$", payload_sha256):
        raise AuthorizationError("shadow observation digest is invalid")
    legacy_ack_sha256 = hashlib.sha256(legacy_ack_bytes).hexdigest()
    if legacy_ack_sha256 != signed_event.get("legacy_ack_sha256"):
        raise AuthorizationError("shadow observation legacy ack mismatch")
    return {
        "schema": SHADOW_OBSERVATION_SCHEMA,
        "event_id": event_id,
        "verification_status": "verified",
        "payload_sha256": payload_sha256,
        "legacy_delivery_required": True,
        "legacy_ack_sha256": legacy_ack_sha256,
        "legacy_ack": _base64_encode(legacy_ack_bytes),
    }


def validate_signed_ack(message, public_key_der, identity):
    allowed = set([
        "schema", "authorization_protocol_version", "session_id",
        "sender_credential_id", "destination_credential_id", "request_nonce",
        "event_id", "payload", "payload_sha256", "signature",
    ])
    if not isinstance(message, dict) or set(message.keys()) != allowed:
        raise AuthorizationError("signed ack fields are invalid")
    sender = _credential(message.get("sender_credential_id"), "sender_credential_id")
    if credential_id_for_public_key(public_key_der) != sender:
        raise AuthorizationError("signed ack public key mismatch")
    signature = _base64_decode(message.get("signature"), "signature", maximum_bytes=80)
    validate_signature_der(signature)
    if not identity.verify(ack_transcript(message), signature, sender, public_key_der):
        raise AuthorizationError("signed ack signature is invalid")
    return _base64_decode(message.get("payload"), "payload", maximum_bytes=MAX_EVENT_MESSAGE_BYTES)


def continuity_is_stale(last_direct_contact_at, last_nightscout_confirmed_at, now=None):
    now = time.time() if now is None else now
    anchors = []
    for value in (last_direct_contact_at, last_nightscout_confirmed_at):
        if isinstance(value, (int, float)) and value <= now + FUTURE_CLOCK_SKEW_SECONDS:
            anchors.append(value)
    if not anchors:
        return True
    return now - max(anchors) >= CONTINUITY_STALE_SECONDS


class TokenBucket(object):
    def __init__(self, capacity, refill_seconds, monotonic=None):
        self.capacity = float(capacity)
        self.refill_seconds = float(refill_seconds)
        self.monotonic = monotonic or time.monotonic
        self.tokens = float(capacity)
        self.last = self.monotonic()

    def consume(self, amount=1.0):
        now = self.monotonic()
        elapsed = max(0.0, now - self.last)
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed / self.refill_seconds)
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True


class ChallengeStore(object):
    def __init__(self, monotonic=None, maximum=128):
        self.monotonic = monotonic or time.monotonic
        self.maximum = maximum
        self._challenges = {}

    def issue(self, connection_id):
        now = self.monotonic()
        expired = [key for key, value in self._challenges.items() if now > value["expires"]]
        for key in expired:
            self._challenges.pop(key, None)
        if connection_id not in self._challenges and len(self._challenges) >= self.maximum:
            oldest = min(self._challenges.items(), key=lambda item: item[1]["expires"])[0]
            self._challenges.pop(oldest, None)
        challenge = _base64_encode(os.urandom(CHALLENGE_BYTES))
        self._challenges[connection_id] = {
            "challenge": challenge,
            "expires": now + CHALLENGE_LIFETIME_SECONDS,
            "consumed": False,
        }
        return challenge

    def validate(self, connection_id, challenge):
        state = self._challenges.get(connection_id)
        if not state or state["consumed"] or self.monotonic() > state["expires"]:
            raise AuthorizationError("authorization challenge is unavailable")
        if state["challenge"] != _canonical_challenge(challenge, "rig_challenge"):
            raise AuthorizationError("authorization challenge mismatch")

    def consume(self, connection_id, challenge):
        self.validate(connection_id, challenge)
        state = self._challenges[connection_id]
        state["consumed"] = True

    def remove(self, connection_id):
        self._challenges.pop(connection_id, None)


class SessionStore(object):
    def __init__(
        self,
        monotonic=None,
        maximum_per_credential=MAX_SESSIONS_PER_CREDENTIAL,
        maximum_global=MAX_SESSIONS_GLOBAL,
    ):
        self.monotonic = monotonic or time.monotonic
        self.maximum_per_credential = int(maximum_per_credential)
        self.maximum_global = int(maximum_global)
        if self.maximum_per_credential < 1 or self.maximum_global < 1:
            raise ValueError("authorization session bounds are invalid")
        self._sessions = {}

    def _prune(self):
        now = self.monotonic()
        expired = [key for key, value in self._sessions.items() if (
            now - value["created"] >= SESSION_ABSOLUTE_SECONDS or
            now - value["last_used"] >= SESSION_IDLE_SECONDS
        )]
        for key in expired:
            self._sessions.pop(key, None)

    def create(self, phone_credential_id, rig_credential_id, connection_id=None, session_id=None):
        self._prune()
        phone_credential_id = _credential(phone_credential_id, "phone_credential_id")
        rig_credential_id = _credential(rig_credential_id, "rig_credential_id")
        existing = sorted(
            [(key, value) for key, value in self._sessions.items() if value["phone"] == phone_credential_id],
            key=lambda item: item[1]["created"],
        )
        while len(existing) >= self.maximum_per_credential:
            key, _value = existing.pop(0)
            self._sessions.pop(key, None)
        while len(self._sessions) >= self.maximum_global:
            oldest = min(self._sessions.items(), key=lambda item: item[1]["created"])[0]
            self._sessions.pop(oldest, None)
        identifier = str(uuid.UUID(session_id)) if session_id else str(uuid.uuid4())
        now = self.monotonic()
        self._sessions[identifier] = {
            "phone": phone_credential_id,
            "rig": rig_credential_id,
            "connection": connection_id,
            "created": now,
            "last_used": now,
            "nonces": [],
        }
        return identifier

    def require(self, session_id, phone_credential_id, rig_credential_id, connection_id=None, nonce=None):
        self._prune()
        identifier = _uuid(session_id, "session_id")
        state = self._sessions.get(identifier)
        if not state:
            raise AuthorizationError("authorization session is unavailable")
        if state["phone"] != phone_credential_id or state["rig"] != rig_credential_id:
            raise AuthorizationError("authorization session peer mismatch")
        if state["connection"] is not None and state["connection"] != connection_id:
            raise AuthorizationError("authorization session connection mismatch")
        if nonce is not None:
            nonce = _canonical_challenge(nonce, "message_nonce")
            if nonce in state["nonces"]:
                raise AuthorizationError("authorization nonce was replayed")
        state["last_used"] = self.monotonic()
        return state

    def consume_nonce(self, session_id, phone_credential_id, rig_credential_id, nonce, connection_id=None):
        state = self.require(
            session_id,
            phone_credential_id,
            rig_credential_id,
            connection_id=connection_id,
            nonce=nonce,
        )
        state["nonces"].append(nonce)
        if len(state["nonces"]) > 256:
            state["nonces"] = state["nonces"][-128:]

    def invalidate_credential(self, credential_id):
        credential_id = _credential(credential_id)
        for key in [key for key, value in self._sessions.items() if value["phone"] == credential_id]:
            self._sessions.pop(key, None)

    def invalidate_connection(self, connection_id):
        for key in [key for key, value in self._sessions.items() if value["connection"] == connection_id]:
            self._sessions.pop(key, None)
