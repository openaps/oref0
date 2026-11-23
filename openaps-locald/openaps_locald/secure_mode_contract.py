"""Signed supervisor generation shared by HTTP and BLE secure-mode owners.

Caller-supplied live scope and process instance IDs are the authority. Stored
bytes cannot select or refresh them, and this contract is never admission.
"""
import base64
import json
import re
import uuid
from collections import namedtuple

from .stored_proof import _object
from .write_challenge import ChallengeError


SCHEMA = "openaps.secure-mode-readiness.v1"
DOMAIN = b"openaps-secure-mode-readiness-signature-v1\0"
MAX_BYTES = 2048
Binding = namedtuple("Binding", "authority local_credential_id settings_epoch key_epoch "
                     "policy_generation policy_review_sha256 http_instance ble_instance")


class ContractMissing(ChallengeError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _binding(value):
    if (not isinstance(value, Binding) or
            re.fullmatch("ns_[0-9a-f]{64}", value.authority) is None or
            re.fullmatch("[0-9a-f]{64}", value.local_credential_id) is None or
            re.fullmatch("[0-9a-f]{64}", value.policy_review_sha256) is None or
            not all(isinstance(item, uuid.UUID) and item.int != 0 for item in
                    (value.settings_epoch, value.key_epoch, value.policy_generation,
                     value.http_instance, value.ble_instance))):
        raise ChallengeError("secure-mode contract binding")
    return value


def _unsigned(binding, generation, phase="committed"):
    _binding(binding)
    if not isinstance(generation, uuid.UUID) or generation.int == 0:
        raise ChallengeError("secure-mode contract generation")
    if phase not in ("prepared", "committed", "aborted"):
        raise ChallengeError("secure-mode contract phase")
    return {"schema": SCHEMA, "generation": str(generation), "phase": phase,
        "authority": binding.authority, "local_credential_id": binding.local_credential_id,
        "settings_epoch": str(binding.settings_epoch), "key_epoch": str(binding.key_epoch),
        "policy_generation": str(binding.policy_generation),
        "policy_review_sha256": binding.policy_review_sha256,
        "http_instance": str(binding.http_instance), "ble_instance": str(binding.ble_instance)}


def encode(binding, generation, identity, phase="committed"):
    fields = _unsigned(binding, generation, phase)
    if identity.credential_id != binding.local_credential_id:
        raise ChallengeError("secure-mode contract identity")
    fields["signature"] = base64.b64encode(identity.sign(DOMAIN + _json(fields))).decode("ascii")
    data = _json(fields)
    if len(data) > MAX_BYTES:
        raise ChallengeError("secure-mode contract size")
    return data


def decode_record(data, expected, identity):
    expected = _binding(expected)
    observed, generation, phase = decode_signed_record(data, identity)
    if observed != expected:
        raise ChallengeError("secure-mode contract scope or signature")
    return generation, phase


def decode_signed_record(data, identity):
    """Verify and decode a signed contract before using stored scope fields.

    This helper is for restart coordination only.  Callers must still compare
    the returned binding with their current live scope and process instances.
    """
    obj = _object(data, maximum_bytes=MAX_BYTES, maximum_depth=1)
    names = {"schema", "generation", "phase", "authority",
             "local_credential_id", "settings_epoch", "key_epoch",
             "policy_generation", "policy_review_sha256", "http_instance",
             "ble_instance", "signature"}
    if (not isinstance(obj, dict) or set(obj) != names or
            any(not isinstance(value, str) for value in obj.values()) or
            obj.get("schema") != SCHEMA or _json(obj) != data):
        raise ChallengeError("secure-mode contract shape")
    fields = dict(obj)
    encoded_signature = fields.pop("signature")
    try:
        generation = uuid.UUID(fields["generation"])
        observed = Binding(fields["authority"], fields["local_credential_id"],
            uuid.UUID(fields["settings_epoch"]), uuid.UUID(fields["key_epoch"]),
            uuid.UUID(fields["policy_generation"]), fields["policy_review_sha256"],
            uuid.UUID(fields["http_instance"]), uuid.UUID(fields["ble_instance"]))
        signature = base64.b64decode(encoded_signature, validate=True)
    except (ValueError, TypeError):
        raise ChallengeError("secure-mode contract encoding") from None
    phase = fields.get("phase")
    _binding(observed)
    if (fields != _unsigned(observed, generation, phase) or
            identity.credential_id != observed.local_credential_id or
            not identity.verify(DOMAIN + _json(fields), signature,
                                observed.local_credential_id, identity.public_key_der)):
        raise ChallengeError("secure-mode contract scope or signature")
    return observed, generation, phase


def decode(data, expected, identity):
    generation, phase = decode_record(data, expected, identity)
    if phase != "committed":
        raise ChallengeError("secure-mode contract is not committed")
    return generation


class SecureModeContractStore(object):
    def __init__(self, storage, identity):
        self.storage, self.identity = storage, identity

    def issue(self, expected, generation):
        data = encode(expected, generation, self.identity)
        previous = self.storage.load()
        self.storage.replace(data, expecting=previous)
        if self.storage.load() != data:
            raise ChallengeError("secure-mode contract readback")

    def prepare(self, expected, generation):
        data = encode(expected, generation, self.identity, "prepared")
        previous = self.storage.load()
        self.storage.replace(data, expecting=previous)
        if self.storage.load() != data:
            raise ChallengeError("secure-mode contract readback")

    def commit(self, expected, generation):
        previous = self.storage.load()
        if previous is None or decode_record(previous, expected, self.identity) != (generation, "prepared"):
            raise ChallengeError("secure-mode prepared generation changed")
        data = encode(expected, generation, self.identity, "committed")
        try:
            self.storage.replace(data, expecting=previous)
        except Exception:
            # A durable replace may have crossed its filesystem commit point
            # before reporting an I/O/readback error.  If the exact signed
            # committed bytes are present, treating that outcome as success is
            # safer than asking the supervisor to abort a contract that is
            # already visible to both owners.  Any other outcome remains a
            # failure and the caller must keep enforcement unavailable.
            try:
                if self.storage.load() == data:
                    return
            except Exception:
                pass
            raise
        if self.storage.load() != data:
            raise ChallengeError("secure-mode commit readback")

    def abort(self, expected, generation):
        previous = self.storage.load()
        if previous is None:
            return
        observed, phase = decode_record(previous, expected, self.identity)
        if observed != generation or phase == "committed":
            raise ChallengeError("secure-mode abort generation changed")
        data = encode(expected, generation, self.identity, "aborted")
        self.storage.replace(data, expecting=previous)

    def load(self, expected):
        data = self.storage.load()
        if data is None:
            raise ContractMissing("secure-mode contract missing")
        return decode(data, expected, self.identity)
