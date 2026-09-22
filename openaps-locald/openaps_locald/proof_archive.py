"""Bounded multi-context audit archive, never an active admission cache."""
import base64
import binascii
import hashlib
import json
import re

from . import stored_proof
from .write_challenge import ChallengeError

SCHEMA = "openaps.ns-proof-archive.v1"
MAX_RECORDS = 32
MAX_BYTES = 128 * 1024


def _hex(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def _key(authority, local, peer):
    if not (isinstance(authority, str) and authority.startswith("ns_") and
            _hex(authority[3:]) and _hex(local) and _hex(peer)):
        raise ChallengeError("archive context shape")
    return hashlib.sha256("\0".join((SCHEMA, authority, local, peer)).encode("utf-8")).hexdigest()


class ProofArchive:
    def __init__(self, data=None):
        self._records = {}
        if data is None:
            return
        obj = stored_proof._object(data, maximum_bytes=MAX_BYTES, maximum_depth=3)
        if (not isinstance(obj, dict) or set(obj) != {"schema", "records"} or obj["schema"] != SCHEMA or
                not isinstance(obj["records"], dict) or len(obj["records"]) > MAX_RECORDS):
            raise ChallengeError("archive shape or record limit")
        try:
            for key, encoded in obj["records"].items():
                if not _hex(key) or not isinstance(encoded, str) or len(encoded) > 10924:
                    raise ChallengeError("archive entry shape")
                value = base64.b64decode(encoded, validate=True)
                if (not 0 < len(value) <= stored_proof.MAX_BYTES or
                        base64.b64encode(value).decode("ascii") != encoded):
                    raise ChallengeError("archive entry bounds")
                self._records[key] = value
        except (ValueError, binascii.Error):
            raise ChallengeError("archive entry encoding") from None

    @property
    def count(self):
        return len(self._records)

    def encoded(self):
        obj = {"schema": SCHEMA, "records": {
            key: base64.b64encode(value).decode("ascii") for key, value in self._records.items()}}
        data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if self.count > MAX_RECORDS or len(data) > MAX_BYTES:
            raise ChallengeError("archive capacity")
        return data

    def inserting(self, proof, verifier_identity):
        """Return a separate candidate; no disk write or freshness renewal."""
        fields = proof.challenge
        key = _key(fields["authority_context_id"], fields["verifier_credential_id"], fields["peer_credential_id"])
        if key not in self._records and self.count >= MAX_RECORDS:
            raise ChallengeError("archive record capacity")
        data = stored_proof.encode(proof, proof.policy_review_sha256, verifier_identity)
        result = ProofArchive()
        result._records = dict(self._records)
        result._records[key] = data
        result.encoded()
        return result

    def proof(self, authority, local, local_kind, peer, review, verifier_identity):
        value = self._records.get(_key(authority, local, peer))
        if value is None:
            return None
        return stored_proof.decode(value, authority, local, local_kind, peer, review, verifier_identity)
