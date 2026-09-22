"""Historical signed recovery audit, never live evidence or continuity."""
import base64
import hashlib
import json
import math
import re
import uuid
from collections import namedtuple

from . import recovery_challenge as codec
from .recovery_exchange import RecoveryExchange
from .stored_proof import _object
from .write_challenge import ChallengeError

SCHEMA = "openaps.recovery-audit.v1"
MAX_BYTES = 8192
RecoveryAudit = namedtuple("RecoveryAudit", "recovery_commit_id age_before_write_ms encoded")


def _json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("ascii")


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def decode(data, candidate, identity):
    obj = _object(data, maximum_bytes=MAX_BYTES, maximum_depth=1)
    names = {"schema", "base_commit_id", "candidate_sha256", "recovery_commit_id", "request",
             "signed_response", "witness_public_key_der", "age_before_write_ms"}
    if (not isinstance(obj, dict) or set(obj) != names or
            any(not isinstance(v, str) for v in obj.values()) or obj["schema"] != SCHEMA or _json(obj) != data):
        raise ChallengeError("recovery audit shape")
    try:
        revision = uuid.UUID(obj["recovery_commit_id"])
        if (str(revision) != obj["recovery_commit_id"] or revision.int == 0 or revision == candidate.commit_id or
                obj["base_commit_id"] != str(candidate.commit_id) or
                obj["candidate_sha256"] != hashlib.sha256(candidate.encoded).hexdigest() or
                not re.fullmatch(r"0|[1-9][0-9]{0,7}", obj["age_before_write_ms"])):
            raise ChallengeError("recovery audit binding")
        fields = {}
        for name in ("request", "signed_response", "witness_public_key_der"):
            raw = base64.b64decode(obj[name], validate=True)
            if _b64(raw) != obj[name]:
                raise ChallengeError("recovery audit encoding")
            fields[name] = raw
        request = codec.decode_request(fields["request"])
        context = candidate.context
        if (codec.encode_request(request) != fields["request"] or
                request["authority_context_id"] != context.authority or
                request["requester_credential_id"] != context.local_credential_id or
                request["requester_device_kind"] != context.local_kind or
                request["witness_credential_id"] != context.peer_credential_id or
                fields["witness_public_key_der"] != candidate.proof.public_key_der or
                identity.credential_id != context.local_credential_id):
            raise ChallengeError("recovery audit context")
        codec.verify_response_data(request, fields["signed_response"], fields["witness_public_key_der"], identity)
        signed_age_ms = int(_object(fields["signed_response"], maximum_bytes=codec.MAX_BYTES,
                                   maximum_depth=1)["contact_age_ms"])
        age = int(obj["age_before_write_ms"])
        if not signed_age_ms <= age < 86400000:
            raise ChallengeError("recovery audit age")
        return RecoveryAudit(revision, age, bytes(data))
    except (ValueError, TypeError):
        raise ChallengeError("malformed recovery audit") from None


def prepare(candidate, identity, exchange, evidence):
    if not isinstance(exchange, RecoveryExchange):
        raise ChallengeError("live recovery exchange required")
    age = exchange.current_contact_age(evidence)  # Identity-bound evidence only.
    obj = dict(schema=SCHEMA, base_commit_id=str(candidate.commit_id),
               candidate_sha256=hashlib.sha256(candidate.encoded).hexdigest(),
               recovery_commit_id=str(uuid.uuid4()), request=_b64(codec.encode_request(dict(evidence.request))),
               signed_response=_b64(evidence.signed_response), witness_public_key_der=_b64(evidence.witness_public_key_der),
               age_before_write_ms=str(int(math.ceil(age * 1000))))
    audit = decode(_json(obj), candidate, identity)
    age_ms = int(math.ceil(exchange.current_contact_age(evidence) * 1000))
    if age_ms >= 86400000:
        raise ChallengeError("recovery rounded age expired")
    obj["age_before_write_ms"] = str(age_ms)
    return RecoveryAudit(audit.recovery_commit_id, age_ms, _json(obj))
