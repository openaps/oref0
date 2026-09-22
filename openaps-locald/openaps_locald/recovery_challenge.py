"""Bounded recovery wire/signature codec, never admission or continuity.

The runtime must separately establish exact-peer witness eligibility, reserve
shared resource budgets, consume a fresh request and commit guarded evidence.
"""
import base64
import binascii
import json
import math
import os
import re
import tempfile
import uuid

from .stored_proof import _object
from .write_challenge import ChallengeError
from .device_identity import (IdentityError, credential_id_for_public_key,
    validate_public_key_der, validate_signature_der, _run_openssl)

SCHEMA = "openaps.continuity-request.v1"
RESPONSE_SCHEMA = "openaps.continuity-witness.v1"
ORDER = ("authority_context_id", "requester_credential_id", "requester_device_kind",
    "witness_credential_id", "witness_device_kind", "nonce", "connection_id")
NAMES = set(ORDER) | {"schema"}
MAX_BYTES = 4096


def validate_request(fields):
    if (not isinstance(fields, dict) or set(fields) != NAMES or
            not all(isinstance(value, str) for value in fields.values()) or
            fields["schema"] != SCHEMA):
        raise ChallengeError("recovery request shape")
    if (not re.fullmatch(r"ns_[0-9a-f]{64}", fields["authority_context_id"]) or
            not all(re.fullmatch(r"[0-9a-f]{64}", fields[name]) for name in
                ("requester_credential_id", "witness_credential_id", "nonce")) or
            fields["requester_credential_id"] == fields["witness_credential_id"] or
            {fields["requester_device_kind"], fields["witness_device_kind"]} != {"phone", "rig"}):
        raise ChallengeError("recovery request context")
    try:
        if str(uuid.UUID(fields["connection_id"])) != fields["connection_id"]:
            raise ValueError()
    except ValueError:
        raise ChallengeError("recovery connection identity") from None
    return dict(fields)


def fresh_request(authority, requester, requester_kind, witness, witness_kind, connection_id):
    return validate_request(dict(zip(("schema",) + ORDER, (SCHEMA, authority,
        requester, requester_kind, witness, witness_kind,
        binascii.hexlify(os.urandom(32)).decode("ascii"), str(connection_id)))))


def decode_request(data):
    return validate_request(_object(data, maximum_bytes=MAX_BYTES, maximum_depth=1))


def encode_request(fields):
    return json.dumps(validate_request(fields), sort_keys=True, separators=(",", ":")).encode("ascii")


def signing_bytes(request, age_ms):
    fields = validate_request(request)
    return "\x00".join([RESPONSE_SCHEMA] + [fields[name] for name in ORDER] + [age_ms]).encode("ascii")


def signed_response(request, identity, authority, kind, contact_age):
    fields = validate_request(request)
    if (identity.credential_id != fields["witness_credential_id"] or
            authority != fields["authority_context_id"] or kind != fields["witness_device_kind"]):
        raise ChallengeError("recovery signer context")
    if not math.isfinite(contact_age) or not 0 <= contact_age < 86400:
        raise ChallengeError("recovery contact age")
    age = int(math.ceil(contact_age * 1000))
    if age >= 86400000:
        raise ChallengeError("recovery rounded contact age")
    fields.update(schema=RESPONSE_SCHEMA, contact_age_ms=str(age),
        signature=base64.b64encode(identity.sign(signing_bytes(request, str(age)))).decode("ascii"))
    return fields


def verify_response(request, response, public_key_der, verifier_identity):
    fields = validate_request(request)
    if (not isinstance(response, dict) or set(response) != NAMES | {"contact_age_ms", "signature"} or
            not all(isinstance(value, str) for value in response.values()) or
            response["schema"] != RESPONSE_SCHEMA or
            any(response[name] != fields[name] for name in ORDER)):
        raise ChallengeError("recovery response shape")
    age = response["contact_age_ms"]
    if not re.fullmatch(r"0|[1-9][0-9]{0,7}", age) or int(age) >= 86400000:
        raise ChallengeError("recovery response age")
    if (not isinstance(public_key_der, bytes) or len(public_key_der) != 91 or
            credential_id_for_public_key(public_key_der) != fields["witness_credential_id"] or
            len(response["signature"]) > 104):
        raise ChallengeError("recovery response key or signature")
    try:
        signature = base64.b64decode(response["signature"], validate=True)
        if base64.b64encode(signature).decode("ascii") != response["signature"]:
            raise ValueError()
        validate_signature_der(signature)
        validate_public_key_der(public_key_der, verifier_identity.openssl_path, verifier_identity.openssl_lock_path)
        # Do not place an unproven key in the persistent peer cache.
        with tempfile.TemporaryDirectory(prefix="openaps-recovery-signature-") as directory:
            key_path = os.path.join(directory, "key.der")
            signature_path = os.path.join(directory, "signature.der")
            for path, data in ((key_path, public_key_der), (signature_path, signature)):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
            _run_openssl([verifier_identity.openssl_path, "dgst", "-sha256", "-verify", key_path,
                "-keyform", "DER", "-signature", signature_path], input_bytes=signing_bytes(request, age),
                lock_path=verifier_identity.openssl_lock_path)
    except (IdentityError, ValueError, binascii.Error):
        raise ChallengeError("recovery response signature") from None
    return int(age) / 1000.0


def verify_response_data(request, data, public_key_der, verifier_identity):
    return verify_response(request, _object(data, maximum_bytes=MAX_BYTES, maximum_depth=1),
        public_key_der, verifier_identity)
