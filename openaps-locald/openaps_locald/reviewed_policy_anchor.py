"""Signed durable policy generation, never current Nightscout evidence.

The caller supplies every expected scope field from current local state. Stored
bytes cannot select authority, epochs, key, role or review statement. Restoring
an anchor permits restricted recovery checks only; fresh enrollment separately
requires live opaque policy evidence.
"""
import base64
import json
import re
import threading
import uuid
from collections import namedtuple

from .stored_proof import _object
from .write_challenge import ChallengeError


SCHEMA = "openaps.reviewed-policy-anchor.v1"
MAX_BYTES = 2048
SIGNATURE_DOMAIN = b"openaps-reviewed-policy-anchor-signature-v1\0"
Binding = namedtuple("Binding", "authority local_credential_id local_kind settings_epoch "
                     "local_key_generation review_sha256")


class PolicyAnchorMissing(ChallengeError):
    """Authoritative absence only; malformed or uncertain storage is different."""
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _binding(value):
    if (not isinstance(value, Binding) or
            re.fullmatch("ns_[0-9a-f]{64}", value.authority) is None or
            re.fullmatch("[0-9a-f]{64}", value.local_credential_id) is None or
            value.local_kind not in ("phone", "rig") or
            re.fullmatch("[0-9a-f]{64}", value.review_sha256) is None or
            not all(isinstance(item, uuid.UUID) and item.int != 0 for item in
                    (value.settings_epoch, value.local_key_generation))):
        raise ChallengeError("policy anchor binding")
    return value


def _unsigned(binding, generation):
    _binding(binding)
    if not isinstance(generation, uuid.UUID) or generation.int == 0:
        raise ChallengeError("policy anchor generation")
    return {"schema": SCHEMA, "authority": binding.authority,
        "local_credential_id": binding.local_credential_id,
        "local_kind": binding.local_kind,
        "settings_epoch": str(binding.settings_epoch),
        "local_key_generation": str(binding.local_key_generation),
        "review_sha256": binding.review_sha256,
        "policy_generation": str(generation)}


def encode(binding, generation, identity):
    fields = _unsigned(binding, generation)
    if identity.credential_id != binding.local_credential_id:
        raise ChallengeError("policy anchor identity")
    signature = identity.sign(SIGNATURE_DOMAIN + _json(fields))
    fields["signature"] = base64.b64encode(signature).decode("ascii")
    data = _json(fields)
    if len(data) > MAX_BYTES:
        raise ChallengeError("policy anchor size")
    return data


def decode(data, expected, identity):
    expected = _binding(expected)
    obj = _object(data, maximum_bytes=MAX_BYTES, maximum_depth=1)
    names = {"schema", "authority", "local_credential_id", "local_kind",
             "settings_epoch", "local_key_generation", "review_sha256",
             "policy_generation", "signature"}
    if (not isinstance(obj, dict) or set(obj) != names or
            any(not isinstance(value, str) for value in obj.values()) or
            obj["schema"] != SCHEMA or _json(obj) != data):
        raise ChallengeError("policy anchor shape")
    fields = dict(obj)
    encoded_signature = fields.pop("signature")
    try:
        generation = uuid.UUID(fields["policy_generation"])
        settings = uuid.UUID(fields["settings_epoch"])
        key = uuid.UUID(fields["local_key_generation"])
        signature = base64.b64decode(encoded_signature, validate=True)
    except (ValueError, TypeError):
        raise ChallengeError("policy anchor encoding") from None
    observed = Binding(fields["authority"], fields["local_credential_id"],
        fields["local_kind"], settings, key, fields["review_sha256"])
    if (observed != expected or fields != _unsigned(expected, generation) or
            base64.b64encode(signature).decode("ascii") != encoded_signature or
            identity.credential_id != expected.local_credential_id or
            not identity.verify(SIGNATURE_DOMAIN + _json(fields), signature,
                                identity.credential_id, identity.public_key_der)):
        raise ChallengeError("policy anchor scope or signature")
    return generation


class PolicyAnchorStore(object):
    def __init__(self, storage, identity):
        if (not callable(getattr(storage, "load", None)) or
                not callable(getattr(storage, "replace", None))):
            raise ChallengeError("policy anchor storage")
        self.storage, self.identity = storage, identity
        self.lock, self.valid = threading.Lock(), True

    def load(self, expected):
        with self.lock:
            if not self.valid:
                raise ChallengeError("policy anchor unavailable")
            data = self.storage.load()
            if data is None:
                raise PolicyAnchorMissing("policy anchor missing")
            return decode(data, expected, self.identity)

    def load_or_create(self, expected):
        """Called only after the policy owner consumes fresh opaque evidence."""
        with self.lock:
            if not self.valid:
                raise ChallengeError("policy anchor unavailable")
            previous = self.storage.load()
            if previous is not None:
                return decode(previous, expected, self.identity)
            generation = uuid.uuid4()
            data = encode(expected, generation, self.identity)
            attempted = False
            try:
                attempted = True
                self.storage.replace(data, expecting=None)
                if self.storage.load() != data:
                    raise ChallengeError("policy anchor readback")
                return generation
            except Exception:
                if attempted:
                    self.valid = False
                raise ChallengeError("policy anchor outcome ambiguous") from None

    def invalidate(self):
        with self.lock:
            self.valid = False
