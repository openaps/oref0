"""Exact-key durable epoch prerequisite; this does not grant recovery admission.

Inject private, atomic CAS storage implementing load() and replace(bytes,
expecting=None). AdmissionStorage is suitable ONLY in a dedicated epoch
directory, never the admission candidate directory. No default path is chosen.
An ambiguous write poisons this instance; a restart must read durable bytes.
"""
import json
import re
import threading
import uuid

MAX_BYTES = 256
SCHEMA = "openaps.key-epoch.v1"


class KeyEpochError(Exception):
    pass


def _key(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise KeyEpochError("invalid key credential")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise KeyEpochError("duplicate epoch field")
        result[key] = value
    return result


def _decode(data, key):
    try:
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
            raise ValueError()
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
        if (not isinstance(value, dict) or set(value) != {"schema", "key_credential_id", "epoch"}
                or value["schema"] != SCHEMA
                or value["key_credential_id"] != key or not isinstance(value["epoch"], str)):
            raise ValueError()
        epoch = uuid.UUID(value["epoch"])
        if str(epoch) != value["epoch"] or epoch.int == 0:
            raise ValueError()
        return epoch
    except Exception:
        raise KeyEpochError("missing or invalid exact-key epoch") from None


class KeyEpochStore:
    def __init__(self, storage):
        if not callable(getattr(storage, "load", None)) or not callable(getattr(storage, "replace", None)):
            raise KeyEpochError("atomic private storage required")
        self.storage = storage
        self._lock = threading.Lock()
        self._valid = True

    def _check(self):
        if not self._valid:
            raise KeyEpochError("epoch storage outcome ambiguous")

    def load_existing(self, key_credential_id):
        key = _key(key_credential_id)
        with self._lock:
            self._check()
            return _decode(self.storage.load(), key)

    def bootstrap_fresh_enrollment(self, key_credential_id):
        """Explicit fresh-enrollment operation, never a restore fallback."""
        key = _key(key_credential_id)
        with self._lock:
            self._check()
            current = self.storage.load()
            if current is not None:
                return _decode(current, key)  # Never repair corrupt/wrong-key bytes.
            epoch = uuid.uuid4()
            data = json.dumps({"schema": SCHEMA, "key_credential_id": key, "epoch": str(epoch)},
                              sort_keys=True, separators=(",", ":")).encode("utf-8")
            try:
                self.storage.replace(data, expecting=None)
                observed = self.storage.load()
                if observed != data or _decode(observed, key) != epoch:
                    raise KeyEpochError("epoch replacement readback mismatch")
            except Exception:
                self._valid = False
                raise KeyEpochError("epoch storage outcome ambiguous") from None
            return epoch
