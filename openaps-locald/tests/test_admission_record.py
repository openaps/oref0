import json
import unittest
import uuid

from openaps_locald import admission_record
from openaps_locald.write_challenge import ChallengeError, signed_response, response_envelope
from tests import test_nightscout_write_proof


class AdmissionRecordTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_nightscout_write_proof.ProofIOTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        class Anonymous:
            def request_bytes(self, *args, **kwargs):
                return 401, b""
        self.client = f.client(f.phone, "phone", anonymous_transport=Anonymous())
        f.replies = [(200, b'{"check":true}')]
        self.before = self.client.observe_enrollment_permissions()
        challenge = self.client.issue_challenge(f.rig.credential_id, "rig")
        response = signed_response(challenge, f.rig, f.authority, "rig")
        f.replies = [(200, b"[" + response_envelope(challenge, response, 1000) + b"]")]
        self.receipt = self.client.read_fresh_peer_response(challenge["nonce"], f.rig.public_key_der)
        f.replies = [(200, b'{"check":true}')]
        self.after = self.client.observe_enrollment_permissions()
        self.context = admission_record.Context(f.authority, f.phone.credential_id, "phone", f.rig.credential_id,
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "b" * 64)

    def prepare(self):
        return admission_record.prepare(self.client, self.receipt, self.before, self.after,
            self.context, self.fixture.phone)

    def decode(self, data, context=None):
        return admission_record.decode(data, context or self.context, self.fixture.phone)

    def test_live_owner_capture_and_recovery_required_restore(self):
        candidate = self.prepare()
        restored = self.decode(candidate.encoded)
        self.assertEqual(restored.commit_id, candidate.commit_id)
        self.assertEqual(restored.proof.response, self.receipt.response)
        self.client.invalidate()
        with self.assertRaises(ChallengeError):
            self.prepare()
        self.decode(candidate.encoded)  # Audit only, no live owner reconstructed.

    def test_context_tamper_and_bounds_rejected(self):
        data = self.prepare().encoded
        for name in ("settings_epoch", "local_key_generation", "policy_generation"):
            with self.assertRaises(ChallengeError):
                self.decode(data, self.context._replace(**{name: uuid.uuid4()}))
        original = json.loads(data.decode("utf-8"))
        for name, value in [("before_id", original["after_id"]), ("before_started", "nan"),
                ("after_finished", "120.0"), ("proof", "bad"), ("unknown", "extra")]:
            obj = dict(original); obj[name] = value
            with self.assertRaises(ChallengeError):
                self.decode(json.dumps(obj).encode("utf-8"))
        for bad in (b"", data[:-1], b" " * (admission_record.MAX_BYTES + 1), b'{"schema":"duplicate",' + data[1:]):
            with self.assertRaises(ChallengeError):
                self.decode(bad)
