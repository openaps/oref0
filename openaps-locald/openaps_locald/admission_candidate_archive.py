"""Bounded multi-peer candidate archive. Never active admission or proof cache."""
import base64
import binascii
import hashlib
import json

from . import admission_record, stored_proof
from .proof_archive import _hex
from .write_challenge import ChallengeError

SCHEMA = "openaps.ns-admission-candidates.v1"
MAX_RECORDS = 32
MAX_BYTES = 128 * 1024


def _key(context):
    if not (isinstance(context.authority, str) and context.authority.startswith("ns_") and
            _hex(context.authority[3:]) and _hex(context.local_credential_id) and _hex(context.peer_credential_id)):
        raise ChallengeError("candidate archive context")
    return hashlib.sha256("\0".join((SCHEMA, context.authority, context.local_credential_id,
        context.peer_credential_id)).encode("ascii")).hexdigest()


class CandidateArchive:
    def __init__(self, data=None):
        self._records = {}
        if data is None:
            return
        obj = stored_proof._object(data, maximum_bytes=MAX_BYTES, maximum_depth=2)
        if (not isinstance(obj, dict) or set(obj) != {"schema", "records"} or obj["schema"] != SCHEMA or
                not isinstance(obj["records"], dict) or len(obj["records"]) > MAX_RECORDS):
            raise ChallengeError("candidate archive shape")
        try:
            for key, text in obj["records"].items():
                if not _hex(key) or not isinstance(text, str) or len(text) > 21848:
                    raise ChallengeError("candidate archive entry")
                data = base64.b64decode(text, validate=True)
                if not 0 < len(data) <= admission_record.MAX_BYTES or base64.b64encode(data).decode("ascii") != text:
                    raise ChallengeError("candidate archive encoding")
                self._records[key] = data
        except (ValueError, binascii.Error):
            raise ChallengeError("candidate archive encoding") from None

    @property
    def count(self):
        return len(self._records)

    def encoded(self):
        data = json.dumps({"schema": SCHEMA, "records": {
            key: base64.b64encode(value).decode("ascii") for key, value in self._records.items()}},
            sort_keys=True, separators=(",", ":")).encode("utf-8")
        if self.count > MAX_RECORDS or len(data) > MAX_BYTES:
            raise ChallengeError("candidate archive capacity")
        return data

    def inserting(self, candidate, verifier_identity):
        # Revalidate even locally supplied candidates, never rely on tuple type.
        candidate = admission_record.decode(candidate.encoded, candidate.context, verifier_identity)
        key = _key(candidate.context)
        if key not in self._records and self.count >= MAX_RECORDS:
            raise ChallengeError("candidate archive capacity")
        result = CandidateArchive()
        result._records = dict(self._records)
        result._records[key] = candidate.encoded
        result.encoded()
        return result

    def candidate(self, context, verifier_identity):
        data = self._records.get(_key(context))
        return None if data is None else admission_record.decode(data, context, verifier_identity)
