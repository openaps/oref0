"""Durable policy generation is recovery scope, never current NS permission."""
import base64
import json
import os
import tempfile
import unittest
import uuid

from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.reviewed_ingress_policy import ReviewedIngressPolicy, _review_sha256
from openaps_locald.reviewed_policy_anchor import Binding, PolicyAnchorStore, decode, encode, MAX_BYTES
from openaps_locald.write_challenge import ChallengeError
from tests import test_nightscout_write_proof


class PolicyAnchorTests(unittest.TestCase):
    def setUp(self):
        self.f = test_nightscout_write_proof.ProofIOTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = tempfile.TemporaryDirectory(prefix="openaps-policy-anchor-")
        self.addCleanup(self.root.cleanup)
        self.path = os.path.join(self.root.name, "anchor")
        os.mkdir(self.path, 0o700)
        self.binding = Binding(self.f.authority, self.f.rig.credential_id, "rig",
            uuid.uuid4(), uuid.uuid4(), _review_sha256(self.f.authority))

    def test_signed_bounded_roundtrip_and_exact_scope(self):
        generation = uuid.uuid4()
        data = encode(self.binding, generation, self.f.rig)
        self.assertLessEqual(len(data), MAX_BYTES)
        self.assertEqual(decode(data, self.binding, self.f.rig), generation)
        values = [
            self.binding._replace(authority="ns_" + "0" * 64),
            self.binding._replace(local_credential_id=self.f.phone.credential_id),
            self.binding._replace(local_kind="phone"),
            self.binding._replace(settings_epoch=uuid.uuid4()),
            self.binding._replace(local_key_generation=uuid.uuid4()),
            self.binding._replace(review_sha256="0" * 64),
        ]
        for changed in values:
            with self.assertRaises(ChallengeError):
                decode(data, changed, self.f.rig)
        obj = json.loads(data.decode("utf-8"))
        signature = base64.b64decode(obj["signature"])
        obj["signature"] = base64.b64encode(signature[:-1] + bytes([signature[-1] ^ 1])).decode("ascii")
        with self.assertRaises(ChallengeError):
            decode(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                   self.binding, self.f.rig)
        with self.assertRaises(ChallengeError):
            decode(data + b" ", self.binding, self.f.rig)
        with self.assertRaises(ChallengeError):
            decode(b"x" * (MAX_BYTES + 1), self.binding, self.f.rig)

    def test_create_reuse_restore_and_live_upgrade_keep_generation(self):
        storage = AdmissionStorage(self.path)
        anchor = PolicyAnchorStore(storage, self.f.rig)
        generation = anchor.load_or_create(self.binding)
        self.assertEqual(anchor.load_or_create(self.binding), generation)
        restored_owner = ReviewedIngressPolicy(PolicyAnchorStore(storage, self.f.rig))
        lease = restored_owner.restore(self.binding)
        self.assertEqual(lease.generation, generation)
        with self.assertRaises(ChallengeError):
            lease.require_fresh()
        client = self._client()
        evidence = self._evidence(client)
        self.assertIs(restored_owner.install(evidence, self.binding), lease)
        lease.require_fresh()
        self.assertEqual(lease.generation, generation)

    def test_invalid_existing_and_ambiguous_create_fail_closed(self):
        storage = AdmissionStorage(self.path)
        storage.replace(b"{}", expecting=None)
        anchor = PolicyAnchorStore(storage, self.f.rig)
        with self.assertRaises(ChallengeError):
            anchor.load_or_create(self.binding)

        class Ambiguous(object):
            def __init__(self):
                self.data = None
            def load(self):
                return self.data
            def replace(self, data, expecting=None):
                self.data = data
                raise IOError("stored then failed")
        ambiguous = PolicyAnchorStore(Ambiguous(), self.f.rig)
        with self.assertRaises(ChallengeError):
            ambiguous.load_or_create(self.binding)
        with self.assertRaises(ChallengeError):
            ambiguous.load(self.binding)

    def _client(self):
        class Anonymous:
            def request_bytes(self, *args, **kwargs):
                return 401, b""
        return self.f.client(self.f.rig, "rig", anonymous_transport=Anonymous())

    def _evidence(self, client):
        self.f.replies = [(200, b'{"check":true}')]
        return client.reviewed_policy_evidence(client.observe_enrollment_permissions())


if __name__ == "__main__":
    unittest.main()
