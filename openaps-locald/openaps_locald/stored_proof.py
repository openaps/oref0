"""Strict local proof/audit codec, never admission or restored freshness.

A review digest is only a local audit reference. The admission owner must
establish policy evidence, local provenance, commit state and continuity.
"""
import base64
import binascii
import json
import math
import re
import uuid
from collections import namedtuple

from .write_challenge import ChallengeError, validate_challenge, verify_response_signature

SCHEMA = "openaps.ns-stored-proof.v1"
SCOPE_VERSION = "openaps.ns-proof-authority.v2"
POLICY_ASSUMPTION = "stable-reviewed-ingress.v1"
MAX_BYTES = 8192
NAMES = {"schema", "scope_version", "policy_assumption", "policy_review_sha256",
    "owner_generation", "issued_monotonic_seconds", "verified_monotonic_seconds",
    "public_key_der", "challenge", "response"}
StoredProofAudit = namedtuple("StoredProofAudit",
    "challenge response public_key_der policy_review_sha256 owner_generation issued_at verified_at")


def _object(data, maximum_bytes=MAX_BYTES, maximum_depth=4):
    if not isinstance(data, bytes) or not 0 < len(data) <= maximum_bytes:
        raise ChallengeError("stored proof size")
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
            if depth > maximum_depth:
                raise ChallengeError("stored proof nesting")
        elif byte in (93, 125):
            depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ChallengeError("duplicate stored proof field")
            result[key] = value
        return result
    def constant(value):
        raise ChallengeError("nonfinite stored proof JSON")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ChallengeError("malformed stored proof JSON") from None


def decode(data, authority, local_credential_id, local_kind, peer_credential_id,
           policy_review_sha256, verifier_identity):
    obj = _object(data)
    try:
        if (not isinstance(obj, dict) or set(obj) != NAMES or
                any(not isinstance(obj[name], str) for name in NAMES - {"challenge", "response"}) or
                obj["schema"] != SCHEMA or obj["scope_version"] != SCOPE_VERSION or
                obj["policy_assumption"] != POLICY_ASSUMPTION or
                not re.fullmatch("[0-9a-f]{64}", obj["policy_review_sha256"])):
            raise ChallengeError("stored proof shape")
        generation = uuid.UUID(obj["owner_generation"])
        issued = float(obj["issued_monotonic_seconds"])
        verified = float(obj["verified_monotonic_seconds"])
        if (str(generation) != obj["owner_generation"] or not math.isfinite(issued) or
                not math.isfinite(verified) or not 0 <= issued <= verified or verified - issued >= 120 or
                str(issued) != obj["issued_monotonic_seconds"] or str(verified) != obj["verified_monotonic_seconds"] or
                len(obj["public_key_der"]) != 124):
            raise ChallengeError("stored proof audit bounds")
        key = base64.b64decode(obj["public_key_der"], validate=True)
        if base64.b64encode(key).decode("ascii") != obj["public_key_der"]:
            raise ChallengeError("stored proof key encoding")
        challenge = validate_challenge(obj["challenge"])
        if (challenge["authority_context_id"] != authority or
                challenge["verifier_credential_id"] != local_credential_id or
                challenge["verifier_device_kind"] != local_kind or
                challenge["peer_credential_id"] != peer_credential_id or
                obj["policy_review_sha256"] != policy_review_sha256):
            raise ChallengeError("stored proof context")
        verify_response_signature(challenge, obj["response"], key, verifier_identity)
        return StoredProofAudit(challenge, dict(obj["response"]), key,
            obj["policy_review_sha256"], generation, issued, verified)
    except (ValueError, TypeError, KeyError, binascii.Error):
        raise ChallengeError("malformed stored proof") from None


def encode(receipt, policy_review_sha256, verifier_identity):
    """Encode a local fresh result; does not check current owner or commit."""
    obj = {"schema": SCHEMA, "scope_version": SCOPE_VERSION, "policy_assumption": POLICY_ASSUMPTION,
        "policy_review_sha256": policy_review_sha256, "owner_generation": str(receipt.owner_generation),
        "issued_monotonic_seconds": str(float(receipt.issued_at)),
        "verified_monotonic_seconds": str(float(receipt.verified_at)),
        "public_key_der": base64.b64encode(receipt.public_key_der).decode("ascii"),
        "challenge": receipt.challenge, "response": receipt.response}
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    fields = receipt.challenge
    decode(data, fields["authority_context_id"], fields["verifier_credential_id"],
        fields["verifier_device_kind"], fields["peer_credential_id"], policy_review_sha256, verifier_identity)
    return data
