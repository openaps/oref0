import json
import os
import tempfile
import unittest
import uuid

from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.nightscout_write_proof import FreshReadback
from openaps_locald.write_challenge import ChallengeError, fresh_challenge, signed_response
from openaps_locald import stored_proof


class StoredProofTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="openaps-stored-proof-")
        self.addCleanup(directory.cleanup)
        self.phone = DeviceIdentity(os.path.join(directory.name, "phone"))
        self.rig = DeviceIdentity(os.path.join(directory.name, "rig"))
        self.authority, self.review = "ns_" + "a" * 64, "b" * 64
        challenge = fresh_challenge(self.authority, self.phone.credential_id, "phone", self.rig.credential_id, "rig")
        response = signed_response(challenge, self.rig, self.authority, "rig")
        # Local synthetic fixture, not an independently retrieved live proof.
        self.receipt = FreshReadback(challenge, response, self.rig.public_key_der, 3.0, 20.0, uuid.uuid4())
        self.data = stored_proof.encode(self.receipt, self.review, self.phone)

    def decode(self, data, **changes):
        args = dict(authority=self.authority, local_credential_id=self.phone.credential_id,
            local_kind="phone", peer_credential_id=self.rig.credential_id,
            policy_review_sha256=self.review, verifier_identity=self.phone)
        args.update(changes)
        return stored_proof.decode(data, **args)

    def test_roundtrip_is_historical_audit_only(self):
        result = self.decode(self.data)
        self.assertEqual(result.challenge, self.receipt.challenge)
        self.assertEqual(result.public_key_der, self.rig.public_key_der)
        self.assertEqual((result.issued_at, result.verified_at), (3, 20))
        self.assertNotIsInstance(result, FreshReadback)
        self.assertFalse(os.path.exists(self.phone.peer_directory))

    def test_wrong_context_rejected(self):
        for name, value in [("authority", "ns_" + "c" * 64), ("local_credential_id", self.rig.credential_id),
                ("local_kind", "rig"), ("peer_credential_id", self.phone.credential_id),
                ("policy_review_sha256", "c" * 64)]:
            with self.assertRaises(ChallengeError):
                self.decode(self.data, **{name: value})

    def test_malformed_legacy_and_tampered_rejected(self):
        original = json.loads(self.data.decode("utf-8"))
        for name, value in [("schema", "legacy"), ("scope_version", "origin-only"),
                ("policy_assumption", "public"), ("subject", "synthetic"),
                ("issued_monotonic_seconds", "nan"), ("issued_monotonic_seconds", "-1.0"),
                ("verified_monotonic_seconds", "123.0"), ("owner_generation", "invalid"),
                ("public_key_der", "A" * 124)]:
            obj = dict(original); obj[name] = value
            with self.assertRaises(ChallengeError):
                self.decode(json.dumps(obj).encode("utf-8"))
        missing = dict(original); del missing["scope_version"]
        duplicate = b'{"schema":"duplicate",' + self.data[1:]
        for data in (b"", self.data[:-1], duplicate, b" " * (stored_proof.MAX_BYTES + 1),
                json.dumps(missing).encode("utf-8")):
            with self.assertRaises(ChallengeError):
                self.decode(data)
        obj = dict(original); obj["response"] = dict(obj["response"], nonce="0" * 64)
        with self.assertRaises(ChallengeError):
            self.decode(json.dumps(obj).encode("utf-8"))
