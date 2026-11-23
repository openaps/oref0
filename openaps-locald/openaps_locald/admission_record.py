"""Scoped candidate audit persistence, never active admission or continuity.

Matches the Swift candidate string-map. A policy digest/generation is a reference,
not reviewed ingress evidence. Decoding never reconstructs live capabilities.
"""
import base64
import binascii
import json
import math
import uuid
from collections import namedtuple

from . import stored_proof
from .write_challenge import ChallengeError

SCHEMA = "openaps.ns-admission-candidate.v1"
MAX_BYTES = 16384
NAMES = {"schema", "settings_epoch", "local_key_generation", "policy_generation",
    "commit_id", "proof", "before_id", "before_started", "before_finished",
    "after_id", "after_started", "after_finished"}
Context = namedtuple("Context", "authority local_credential_id local_kind peer_credential_id "
    "settings_epoch local_key_generation policy_generation policy_review_sha256")
CandidateAudit = namedtuple("CandidateAudit", "context commit_id proof encoded")


def decode(data, expected, verifier_identity):
    obj = stored_proof._object(data, maximum_bytes=MAX_BYTES, maximum_depth=1)
    try:
        if (not isinstance(obj, dict) or set(obj) != NAMES or
                any(not isinstance(value, str) for value in obj.values()) or obj["schema"] != SCHEMA):
            raise ChallengeError("candidate shape")
        def identifier(name):
            value = uuid.UUID(obj[name])
            if str(value) != obj[name]:
                raise ChallengeError("candidate identifier")
            return value
        for name in ("settings_epoch", "local_key_generation", "policy_generation"):
            if identifier(name) != getattr(expected, name):
                raise ChallengeError("candidate context")
        commit = identifier("commit_id")
        if identifier("before_id") == identifier("after_id") or len(obj["proof"]) > 10924:
            raise ChallengeError("candidate audit bounds")
        proof_bytes = base64.b64decode(obj["proof"], validate=True)
        if base64.b64encode(proof_bytes).decode("ascii") != obj["proof"]:
            raise ChallengeError("candidate proof encoding")
        proof = stored_proof.decode(proof_bytes, expected.authority, expected.local_credential_id,
            expected.local_kind, expected.peer_credential_id, expected.policy_review_sha256, verifier_identity)
        def instant(name):
            value = float(obj[name])
            if not math.isfinite(value) or value < 0 or str(value) != obj[name]:
                raise ChallengeError("candidate audit time")
            return value
        start, before_end = instant("before_started"), instant("before_finished")
        after_start, end = instant("after_started"), instant("after_finished")
        if (not start <= before_end <= proof.issued_at <= proof.verified_at <= after_start <= end or
                before_end - start >= 60 or end - after_start >= 60 or end - start >= 120):
            raise ChallengeError("candidate audit ordering")
        return CandidateAudit(expected, commit, proof, bytes(data))
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error):
        raise ChallengeError("malformed candidate") from None


def prepare(client, receipt, before, after, context, verifier_identity):
    """Original live client checks observations; no persistence or trust grant."""
    client.validate_observed_readback(receipt, before, after)
    proof = stored_proof.encode(receipt, context.policy_review_sha256, verifier_identity)
    obj = {"schema": SCHEMA, "settings_epoch": str(context.settings_epoch),
        "local_key_generation": str(context.local_key_generation), "policy_generation": str(context.policy_generation),
        "commit_id": str(uuid.uuid4()), "proof": base64.b64encode(proof).decode("ascii"),
        "before_id": str(before.identifier), "before_started": str(float(before.started_at)),
        "before_finished": str(float(before.finished_at)), "after_id": str(after.identifier),
        "after_started": str(float(after.started_at)), "after_finished": str(float(after.finished_at))}
    return decode(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"),
        context, verifier_identity)
