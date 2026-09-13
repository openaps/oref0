import json
import os
import tempfile
import unittest
import uuid

from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.nightscout_write_proof import FreshReadback
from openaps_locald.write_challenge import ChallengeError, fresh_challenge, signed_response
from openaps_locald import proof_archive, stored_proof


class ProofArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="openaps-proof-archive-")
        self.addCleanup(directory.cleanup)
        self.phone, self.rig, self.other = [DeviceIdentity(os.path.join(directory.name, name))
            for name in ("phone", "rig", "other")]
        self.authority, self.review = "ns_" + "a" * 64, "b" * 64

    def fixture(self, peer):
        fields = fresh_challenge(self.authority, self.phone.credential_id, "phone", peer.credential_id, "rig")
        receipt = FreshReadback(fields, signed_response(fields, peer, self.authority, "rig"),
            peer.public_key_der, 3.0, 20.0, uuid.uuid4())
        data = stored_proof.encode(receipt, self.review, self.phone)
        return stored_proof.decode(data, self.authority, self.phone.credential_id, "phone", peer.credential_id,
            self.review, self.phone)

    def select(self, archive, **changes):
        args = dict(authority=self.authority, local=self.phone.credential_id, local_kind="phone",
            peer=self.rig.credential_id, review=self.review, verifier_identity=self.phone)
        args.update(changes)
        return archive.proof(**args)

    def test_multi_peer_roundtrip_and_context_isolation(self):
        empty = proof_archive.ProofArchive()
        first = self.fixture(self.rig)
        archive = empty.inserting(first, self.phone).inserting(self.fixture(self.other), self.phone)
        self.assertEqual(empty.count, 0)
        restored = proof_archive.ProofArchive(archive.encoded())
        self.assertEqual(restored.count, 2)
        self.assertEqual(self.select(restored).public_key_der, self.rig.public_key_der)
        self.assertEqual(self.select(restored, peer=self.other.credential_id).public_key_der, self.other.public_key_der)
        self.assertIsNone(self.select(restored, authority="ns_" + "c" * 64))
        self.assertIsNone(self.select(restored, local=self.other.credential_id))
        for changes in (dict(local_kind="rig"), dict(review="c" * 64)):
            with self.assertRaises(ChallengeError):
                self.select(restored, **changes)
        self.assertEqual(restored.inserting(first, self.phone).count, 2)
        obj = json.loads(archive.encoded().decode("utf-8"))
        keys = list(obj["records"])
        obj["records"][keys[0]], obj["records"][keys[1]] = obj["records"][keys[1]], obj["records"][keys[0]]
        swapped = proof_archive.ProofArchive(json.dumps(obj).encode("utf-8"))
        with self.assertRaises(ChallengeError):
            self.select(swapped)

    def test_malformed_and_capacity_bounds(self):
        empty = proof_archive.ProofArchive().encoded()
        self.assertEqual(proof_archive.ProofArchive(empty).count, 0)
        excess = json.dumps({"schema": proof_archive.SCHEMA,
            "records": {"%064x" % index: "eA==" for index in range(33)}}).encode("utf-8")
        for data in (b"", empty[:-1], b'{"schema":"duplicate",' + empty[1:],
                b'{"schema":"legacy","records":{}}', excess, b" " * (proof_archive.MAX_BYTES + 1)):
            with self.assertRaises(ChallengeError):
                proof_archive.ProofArchive(data)
