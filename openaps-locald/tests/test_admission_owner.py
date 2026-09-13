import tempfile
import unittest
import uuid

from openaps_locald.admission_owner import AdmissionOwner, LiveAdmissionContext
from openaps_locald.admission_record import Context
from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.authorization_tls import _snapshot, TLSError
from openaps_locald.reviewed_ingress_policy import ReviewedIngressPolicy, _Lease
from openaps_locald.write_challenge import ChallengeError, signed_response, response_envelope
from tests import test_nightscout_write_proof


def synthetic_review_fixture(authority):
    # Deliberate test-only private construction; production has no installer.
    policy = ReviewedIngressPolicy()
    policy._lease = _Lease(policy, authority, uuid.uuid4(), "b" * 64)
    return policy, policy.current(authority)


class AdmissionOwnerTests(unittest.TestCase):
    def fixture(self):
        f = test_nightscout_write_proof.ProofIOTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        class Anonymous:
            def request_bytes(self, *args, **kwargs):
                return 401, b""
        client = f.client(f.rig, "rig", anonymous_transport=Anonymous())
        f.replies = [(200, b'{"check":true}')]
        before = client.observe_enrollment_permissions()
        challenge = client.issue_challenge(f.phone.credential_id, "phone")
        response = signed_response(challenge, f.phone, f.authority, "phone")
        f.replies = [(200, b"[" + response_envelope(challenge, response, 1000) + b"]")]
        receipt = client.read_fresh_peer_response(challenge["nonce"], f.phone.public_key_der)
        f.replies = [(200, b'{"check":true}')]
        after = client.observe_enrollment_permissions()
        policy, lease = synthetic_review_fixture(f.authority)
        context = Context(f.authority, f.rig.credential_id, "rig", f.phone.credential_id,
            uuid.uuid4(), uuid.uuid4(), lease.generation, lease.review_sha256)
        directory = tempfile.TemporaryDirectory(prefix="openaps-owner-candidates-")
        self.addCleanup(directory.cleanup)
        storage = AdmissionStorage(directory.name)
        return f, client, before, receipt, after, policy, lease, context, storage

    def test_default_policy_unavailable(self):
        with self.assertRaises(ChallengeError):
            ReviewedIngressPolicy().current("ns_" + "a" * 64)

    def test_fresh_commit_and_retained_snapshot_invalidation(self):
        for mode in ("settings", "policy", "policy_drop", "owner"):
            f, client, before, receipt, after, policy, lease, context, storage = self.fixture()
            live = LiveAdmissionContext(context)
            reads = [0]
            def validate(expected):
                self.assertEqual(expected, context)
                reads[0] += 1  # Synthetic durable epoch check, never deployment policy.
            owner = AdmissionOwner(client, storage, context, f.rig, live, lease, validate, clock=lambda: f.time)
            with self.assertRaises(ChallengeError):
                owner.snapshot(str(uuid.uuid4()))
            owner.admit_fresh(receipt, before, after)
            first, second = owner.snapshot(str(uuid.uuid4())), owner.snapshot(str(uuid.uuid4()))
            self.assertIs(first["continuity"], second["continuity"])
            count = reads[0]
            self.assertEqual(_snapshot(first, 0)[1], f.phone.public_key_der)
            owner.snapshot(str(uuid.uuid4()))
            for bad in ("not-a-uuid", str(uuid.uuid4()).upper(), None):
                with self.assertRaises(ChallengeError):
                    owner.snapshot(bad)
            self.assertEqual(reads[0], count)
            if mode == "settings":
                live.invalidate()
            elif mode == "policy":
                policy.invalidate()
            elif mode == "policy_drop":
                policy = None
            else:
                owner.invalidate()
            with self.assertRaises((ChallengeError, TLSError)):
                owner.snapshot(str(uuid.uuid4()))
            with self.assertRaises(TLSError):
                _snapshot(first, 0)

    def test_commit_delay_counts_and_postpublication_epoch_error_denies(self):
        for mode in ("delay", "epoch_error"):
            f, client, before, receipt, after, policy, lease, context, real = self.fixture()
            class Storage:
                def load(self):
                    return real.load()
                def replace(self, data, expecting):
                    real.replace(data, expecting=expecting)
                    if mode == "delay":
                        f.time = 100.0
            checks = [0]
            def validate(expected):
                checks[0] += 1
                if mode == "epoch_error" and checks[0] == 8:
                    raise ChallengeError("synthetic changed durable epoch")
            owner = AdmissionOwner(client, Storage(), context, f.rig, LiveAdmissionContext(context), lease,
                validate, clock=lambda: f.time)
            if mode == "epoch_error":
                with self.assertRaises(ChallengeError):
                    owner.admit_fresh(receipt, before, after)
                with self.assertRaises(ChallengeError):
                    owner.snapshot(str(uuid.uuid4()))
            else:
                owner.admit_fresh(receipt, before, after)
                retained = owner.snapshot(str(uuid.uuid4()))
                f.time = 86400.0
                with self.assertRaises(TLSError):
                    _snapshot(retained, 0)  # Anchored before the 100-second commit.
