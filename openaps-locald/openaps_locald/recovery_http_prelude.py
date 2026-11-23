"""Bounded signed HTTP recovery selector; never admission by itself."""
import base64
import json
import re
import uuid

from .stored_proof import _object
from .write_challenge import ChallengeError


SCHEMA = "openaps.http-recovery-prelude.v1"
MAX_BYTES = 2048
SIGNATURE_DOMAIN = b"openaps-http-recovery-prelude-v1\0"
NAMES = {"schema", "authority_context_id", "requester_credential_id",
         "requester_device_kind", "requester_public_key_der",
         "witness_credential_id", "witness_device_kind", "method", "path",
         "nonce", "signature"}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def prepare(identity, authority, witness_credential_id):
    fields = {"schema": SCHEMA, "authority_context_id": authority,
        "requester_credential_id": identity.credential_id,
        "requester_device_kind": "phone",
        "requester_public_key_der": base64.b64encode(identity.public_key_der).decode("ascii"),
        "witness_credential_id": witness_credential_id, "witness_device_kind": "rig",
        "method": "GET", "path": "/v3/recovery", "nonce": str(uuid.uuid4())}
    fields["signature"] = base64.b64encode(identity.sign(
        SIGNATURE_DOMAIN + _json(fields))).decode("ascii")
    data = _json(fields)
    if len(data) > MAX_BYTES:
        raise ChallengeError("recovery prelude size")
    return data


def shape(data):
    obj = _object(data, maximum_bytes=MAX_BYTES, maximum_depth=1)
    if (not isinstance(obj, dict) or set(obj) != NAMES or
            any(not isinstance(value, str) for value in obj.values()) or
            obj["schema"] != SCHEMA or obj["requester_device_kind"] != "phone" or
            obj["witness_device_kind"] != "rig" or obj["method"] != "GET" or
            obj["path"] != "/v3/recovery" or _json(obj) != data or
            re.fullmatch("ns_[0-9a-f]{64}", obj["authority_context_id"]) is None or
            re.fullmatch("[0-9a-f]{64}", obj["requester_credential_id"]) is None or
            re.fullmatch("[0-9a-f]{64}", obj["witness_credential_id"]) is None):
        raise ChallengeError("recovery prelude shape")
    try:
        key = base64.b64decode(obj["requester_public_key_der"], validate=True)
        nonce = uuid.UUID(obj["nonce"])
        signature = base64.b64decode(obj["signature"], validate=True)
    except (ValueError, TypeError):
        raise ChallengeError("recovery prelude encoding") from None
    if (str(nonce) != obj["nonce"] or nonce.int == 0 or
            base64.b64encode(key).decode("ascii") != obj["requester_public_key_der"] or
            base64.b64encode(signature).decode("ascii") != obj["signature"]):
        raise ChallengeError("recovery prelude canonical encoding")
    return obj, key, signature


def verify(data, identity, expected_authority, expected_witness, expected_peer, expected_key):
    fields, key, signature = shape(data)
    unsigned = dict(fields); del unsigned["signature"]
    if (fields["authority_context_id"] != expected_authority or
            fields["witness_credential_id"] != expected_witness or
            fields["requester_credential_id"] != expected_peer or key != expected_key or
            not identity.verify(SIGNATURE_DOMAIN + _json(unsigned), signature,
                                expected_peer, expected_key)):
        raise ChallengeError("recovery prelude rejected")
    return fields["nonce"]
