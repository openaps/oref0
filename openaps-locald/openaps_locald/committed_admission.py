"""Committed-format audit codec ONLY: decoding grants no admission capability.

Only a guarded fresh commit may write this distinct archive to its own private
store. Candidate archives are never migrated. The caller supplies durable
epochs as admission_record.Context; parsed bytes never select expected scope.
Archive construction checks framing; record() verifies the selected signature
and exact externally supplied context. Neither operation restores continuity.
"""
import base64
import hashlib
import json
import math
import uuid
from collections import namedtuple

from . import admission_record, stored_proof, recovery_audit
from .admission_candidate_archive import _key
from .proof_archive import _hex
from .write_challenge import ChallengeError

SCHEMA = "openaps.committed-admission.v1"
ARCHIVE_SCHEMA = "openaps.committed-admissions.v1"
MAX_RECORD_BYTES = 24 * 1024
MAX_BYTES = 128 * 1024
MAX_RECORDS = 32
Audit = namedtuple("Audit", "context commit_id candidate encoded recovery")


def _json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _scope(context, identity):
    _key(context)
    if (context.local_kind not in ("phone", "rig") or
            identity.credential_id != context.local_credential_id or
            not _hex(context.policy_review_sha256)):
        raise ChallengeError("committed context")
    for name in ("settings_epoch", "local_key_generation", "policy_generation"):
        value = getattr(context, name)
        if not isinstance(value, uuid.UUID) or value.int == 0:
            raise ChallengeError("durable epoch required")


def decode(data, expected, verifier_identity):
    _scope(expected, verifier_identity)
    obj = stored_proof._object(data, maximum_bytes=MAX_RECORD_BYTES, maximum_depth=1)
    names = {"schema", "candidate", "candidate_sha256", "commit_id", "authority",
             "local_credential_id", "peer_credential_id", "local_kind", "settings_epoch",
             "local_key_generation", "policy_generation", "policy_review_sha256"}
    if (not isinstance(obj, dict) or set(obj) not in (names, names | {"recovery"}) or
            any(not isinstance(v, str) for v in obj.values()) or obj["schema"] != SCHEMA or
            _json(obj) != data):
        raise ChallengeError("committed record shape or encoding")
    for name in names - {"schema", "candidate", "candidate_sha256", "commit_id"}:
        if obj[name] != str(getattr(expected, name)):
            raise ChallengeError("committed record scope")
    try:
        candidate_bytes = base64.b64decode(obj["candidate"], validate=True)
    except ValueError:
        raise ChallengeError("committed candidate encoding") from None
    if (base64.b64encode(candidate_bytes).decode("ascii") != obj["candidate"] or
            hashlib.sha256(candidate_bytes).hexdigest() != obj["candidate_sha256"]):
        raise ChallengeError("committed candidate digest")
    candidate = admission_record.decode(candidate_bytes, expected, verifier_identity)
    if str(candidate.commit_id) != obj["commit_id"] or candidate.commit_id.int == 0:
        raise ChallengeError("committed base commit")
    recovery = None
    if "recovery" in obj:
        try:
            raw = base64.b64decode(obj["recovery"], validate=True)
        except ValueError:
            raise ChallengeError("recovery revision encoding") from None
        if base64.b64encode(raw).decode("ascii") != obj["recovery"]:
            raise ChallengeError("recovery revision encoding")
        recovery = recovery_audit.decode(raw, candidate, verifier_identity)
    return Audit(expected, candidate.commit_id, candidate, bytes(data), recovery)


def prepare(candidate, expected, verifier_identity):
    """Prepare bytes for a guarded atomic commit; does not perform that commit."""
    candidate = admission_record.decode(candidate.encoded, expected, verifier_identity)
    obj = {name: str(getattr(expected, name)) for name in expected._fields}
    obj.update(schema=SCHEMA, candidate=base64.b64encode(candidate.encoded).decode("ascii"),
               candidate_sha256=hashlib.sha256(candidate.encoded).hexdigest(),
               commit_id=str(candidate.commit_id))
    return decode(_json(obj), expected, verifier_identity)


def prepare_recovery(base, expected, verifier_identity, exchange, evidence):
    """Prepare a revision; caller must guard CAS and recheck age after storage."""
    base = decode(base.encoded, expected, verifier_identity)
    recovery = recovery_audit.prepare(base.candidate, verifier_identity, exchange, evidence)
    if base.recovery is not None and recovery.recovery_commit_id == base.recovery.recovery_commit_id:
        raise ChallengeError("recovery revision reused")
    obj = json.loads(base.encoded.decode("utf-8"))
    obj["recovery"] = base64.b64encode(recovery.encoded).decode("ascii")
    result = decode(_json(obj), expected, verifier_identity)
    age_ms = int(math.ceil(exchange.current_contact_age(evidence) * 1000))
    if age_ms >= 86400000:
        raise ChallengeError("recovery rounded age expired")
    revision = json.loads(recovery.encoded.decode("ascii"))
    revision["age_before_write_ms"] = str(age_ms)
    recovery = recovery_audit.RecoveryAudit(recovery.recovery_commit_id, age_ms, _json(revision))
    obj["recovery"] = base64.b64encode(recovery.encoded).decode("ascii")
    encoded = _json(obj)
    if len(encoded) > MAX_RECORD_BYTES:
        raise ChallengeError("committed revision size")
    return Audit(result.context, result.commit_id, result.candidate, encoded, recovery)


class CommittedArchive:
    def __init__(self, data=None):
        self._records = {}
        if data is None:
            return
        obj = stored_proof._object(data, maximum_bytes=MAX_BYTES, maximum_depth=2)
        if (not isinstance(obj, dict) or set(obj) != {"schema", "records"} or
                obj["schema"] != ARCHIVE_SCHEMA or not isinstance(obj["records"], dict) or
                len(obj["records"]) > MAX_RECORDS or _json(obj) != data):
            raise ChallengeError("committed archive shape or encoding")
        for key, value in obj["records"].items():
            if not _hex(key) or not isinstance(value, str) or len(value) > MAX_RECORD_BYTES * 4 // 3:
                raise ChallengeError("committed archive entry")
            try:
                raw = base64.b64decode(value, validate=True)
            except ValueError:
                raise ChallengeError("committed archive encoding") from None
            if not 0 < len(raw) <= MAX_RECORD_BYTES or base64.b64encode(raw).decode("ascii") != value:
                raise ChallengeError("committed archive bounds")
            self._records[key] = raw

    def encoded(self):
        data = _json({"schema": ARCHIVE_SCHEMA, "records": {
            k: base64.b64encode(v).decode("ascii") for k, v in self._records.items()}})
        if len(self._records) > MAX_RECORDS or len(data) > MAX_BYTES:
            raise ChallengeError("committed archive capacity")
        return data

    def inserting(self, audit, expected, verifier_identity):
        audit = decode(audit.encoded, expected, verifier_identity)
        result = CommittedArchive()
        result._records = dict(self._records)
        result._records[_key(expected)] = audit.encoded
        result.encoded()
        return result

    def record(self, expected, verifier_identity):
        _scope(expected, verifier_identity)
        data = self._records.get(_key(expected))
        return None if data is None else decode(data, expected, verifier_identity)
