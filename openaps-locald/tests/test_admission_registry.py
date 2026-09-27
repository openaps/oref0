"""Synthetic actual-owner registry and TLS tests; no runtime activation."""
import base64
import os
import tempfile
import unittest
import uuid

from openaps_locald.admission_registry import AdmissionRegistry, RegistryScope
from openaps_locald.admission_owner import LiveAdmissionContext
from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.authorization_tls import _snapshot, AdmissionPool, TLSError, TLSServer
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.reverse_enrollment import BEGIN, READY
from openaps_locald.write_challenge import ChallengeError, fresh_challenge, signed_response, response_envelope
from tests import test_nightscout_write_proof, test_authorization_tls
from tests.test_admission_owner import synthetic_review_fixture


class AdmissionRegistryTests(unittest.TestCase):
    def fixture(self, maximum=32):
        f = test_nightscout_write_proof.ProofIOTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        class Anonymous:
            def request_bytes(self, *args, **kwargs):
                return 401, b""
        client = f.client(f.rig, "rig", anonymous_transport=Anonymous())
        policy, lease = synthetic_review_fixture(f.authority)
        scope = RegistryScope(f.authority, f.rig.credential_id, uuid.uuid4(), uuid.uuid4(),
                              lease.generation, lease.review_sha256)
        live = LiveAdmissionContext(scope)
        directory = tempfile.TemporaryDirectory(prefix="openaps-registry-storage-")
        self.addCleanup(directory.cleanup)
        candidates = os.path.join(directory.name, "candidates")
        committed = os.path.join(directory.name, "committed")
        os.mkdir(candidates, 0o700)
        os.mkdir(committed, 0o700)
        registry = AdmissionRegistry(client, f.rig, AdmissionStorage(candidates),
            AdmissionStorage(committed), scope, live, lease,
            lambda expected: self.assertEqual(expected, scope), clock=lambda: f.time, maximum=maximum)
        self.addCleanup(registry.invalidate)
        return f, registry, live, policy

    def begin(self, f, registry):
        a = fresh_challenge(f.authority, f.phone.credential_id, "phone", f.rig.credential_id, "rig")
        body = {"schema": BEGIN, "challenge": a,
            "phone_public_key_der": base64.b64encode(f.phone.public_key_der).decode("ascii")}
        f.replies = [(200, b'{"check":true}')]
        code, result = registry.reverse_workflow.handle(body)
        self.assertEqual(code, 200)
        return result["challenge"]

    def complete(self, f, registry, b):
        response = signed_response(b, f.phone, f.authority, "phone")
        f.replies = [(200, b"[" + response_envelope(b, response, 1000) + b"]"), (200, b'{"check":true}')]
        self.assertEqual(registry.reverse_workflow.handle({"schema": READY, "nonce": b["nonce"]}), (202, None))

    def test_failed_refresh_preserves_old_and_success_replaces_retained_owner(self):
        f, registry, live, policy = self.fixture()
        self.complete(f, registry, self.begin(f, registry))
        old = registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        self.assertEqual(_snapshot(old, 0)[1], f.phone.public_key_der)
        f.time = 120
        b = self.begin(f, registry)
        pending = registry.pending[2]
        self.assertIsNot(pending, registry.active[f.phone.credential_id][1])
        f.replies = [(503, b"")]
        self.assertEqual(registry.reverse_workflow.handle({"schema": READY, "nonce": b["nonce"]}), (503, None))
        self.assertIsNone(registry.pending)
        self.assertEqual(_snapshot(old, 0)[1], f.phone.public_key_der)
        self.assertEqual(registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))["trust_generation"], old["trust_generation"])
        self.complete(f, registry, self.begin(f, registry))
        replacement = registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        self.assertNotEqual(replacement["trust_generation"], old["trust_generation"])
        with self.assertRaises(TLSError):
            _snapshot(old, 0)
        self.assertEqual(_snapshot(replacement, 0)[1], f.phone.public_key_der)

    def test_fresh_admission_replaces_missing_recovery_witness_after_restart(self):
        f, registry, live, policy = self.fixture()
        self.complete(f, registry, self.begin(f, registry))
        scope = registry.scope
        client = registry.client
        candidates = registry.storage
        committed = registry.committed_storage
        lease = registry.policy
        registry.invalidate()

        restarted = AdmissionRegistry(client, f.rig, candidates, committed, scope,
            LiveAdmissionContext(scope), lease,
            lambda expected: self.assertEqual(expected, scope), clock=lambda: f.time)
        self.addCleanup(restarted.invalidate)
        with self.assertRaises(ChallengeError):
            restarted.recovery_witness(f.phone.credential_id, f.phone.public_key_der)

        self.complete(f, restarted, self.begin(f, restarted))
        snapshot = restarted.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        self.assertEqual(_snapshot(snapshot, 0)[1], f.phone.public_key_der)

    def test_capacity_and_context_invalidation_deny_every_retained_snapshot(self):
        for mode in ("settings", "policy", "registry"):
            f, registry, live, policy = self.fixture(maximum=1)
            self.complete(f, registry, self.begin(f, registry))
            snapshot = registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
            # Self-key is never a phone peer and cannot consume registry space.
            with self.assertRaises(ChallengeError):
                registry._fresh_owner(f.rig.public_key_der)
            other = DeviceIdentity(os.path.join(f.directory.name, "other-phone"))
            with self.assertRaises(ChallengeError):
                registry._fresh_owner(other.public_key_der) # Actual full-capacity other peer.
            self.assertIsNone(registry.pending)
            self.assertEqual(_snapshot(snapshot, 0)[1], f.phone.public_key_der)
            with self.assertRaises(ChallengeError):
                registry.snapshot("0" * 64, str(uuid.uuid4()))
            if mode == "settings":
                live.invalidate()
            elif mode == "policy":
                policy.invalidate()
            else:
                registry.invalidate()
            with self.assertRaises(ChallengeError):
                registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
            with self.assertRaises(TLSError):
                _snapshot(snapshot, 0)

    def test_registry_capacity_cannot_be_configured_above_release_bound(self):
        with self.assertRaises(ChallengeError):
            self.fixture(maximum=33)

    def test_factory_handoff_failure_releases_only_exact_fresh_pending_owner(self):
        f, registry, live, policy = self.fixture()
        self.complete(f, registry, self.begin(f, registry))
        old = registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        f.time = 120
        original_factory = registry.reverse_workflow.owner_for_peer
        captured = []
        fail_reads = [False]
        original_validate = registry.validate_persisted
        def validate(scope):
            if fail_reads[0]:
                raise ChallengeError("synthetic transient persisted read")
            original_validate(scope)
        registry.validate_persisted = validate
        def factory(key):
            owner = original_factory(key)
            captured.append(owner)
            fail_reads[0] = True # Fail after registry allocation, before workflow publication.
            return owner
        registry.reverse_workflow.owner_for_peer = factory
        a = fresh_challenge(f.authority, f.phone.credential_id, "phone", f.rig.credential_id, "rig")
        body = {"schema": BEGIN, "challenge": a,
            "phone_public_key_der": base64.b64encode(f.phone.public_key_der).decode("ascii")}
        count = len(f.calls)
        self.assertEqual(registry.reverse_workflow.handle(body), (503, None))
        self.assertEqual(len(f.calls), count)
        self.assertIsNone(registry.pending)
        self.assertIsNone(registry.reverse_workflow.pending)
        fail_reads[0] = False
        with self.assertRaises(ChallengeError):
            captured[0].validate_enrollment_context(registry.client, f.authority, f.rig.credential_id, f.phone.credential_id)
        self.assertEqual(_snapshot(old, 0)[1], f.phone.public_key_der)
        registry.reverse_workflow.owner_for_peer = original_factory
        self.begin(f, registry) # No leaked slot blocks the next bounded attempt.

    def test_completed_tombstone_read_failure_does_not_revoke_active_owner(self):
        f, registry, live, policy = self.fixture()
        b = self.begin(f, registry)
        self.complete(f, registry, b)
        old = registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        original_validate = registry.validate_persisted
        def fail(scope):
            raise ChallengeError("synthetic transient persisted read")
        registry.validate_persisted = fail
        self.assertEqual(registry.reverse_workflow.handle({"schema": READY, "nonce": b["nonce"]}), (503, None))
        self.assertIsNone(registry.reverse_workflow.pending)
        self.assertEqual(_snapshot(old, 0)[1], f.phone.public_key_der)
        registry.validate_persisted = original_validate
        self.assertEqual(registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))["trust_generation"], old["trust_generation"])

    def test_registry_provider_drives_actual_normal_tls_without_shadow_snapshot(self):
        f, registry, live, policy = self.fixture()
        self.complete(f, registry, self.begin(f, registry))
        fixture = test_authorization_tls.TLSReceiverTests()
        fixture.phone, fixture.rig, fixture.directory = f.phone, f.rig, f.directory
        fixture.phone_hello = fixture.certificate(f.phone, 1)
        fixture.rig_hello = fixture.certificate(f.rig, 2)
        pool = AdmissionPool(clock=lambda: f.time)
        provider = registry.provider(f.phone.credential_id, str(uuid.uuid4()))
        server = TLSServer(f.rig, fixture.rig_hello, fixture.phone_hello.encode(), provider,
            clock=lambda: f.time, wall=lambda: 0, admission=pool)
        try:
            fixture.connect(server)
            self.assertTrue(server.ready)
            registry.invalidate()
            with self.assertRaises(TLSError):
                server.tick()
        finally:
            server.close()
        self.assertEqual(pool.entries, {})

    def test_authenticated_contact_refreshes_expired_sibling_marker(self):
        f, registry, live, policy = self.fixture()
        self.complete(f, registry, self.begin(f, registry))
        f.time += 10 * 60
        self.assertIsNone(registry.recently_committed_peer(f.phone.credential_id))
        self.assertEqual(registry.last_recent_commit_failure, "marker_time")

        registry.record_authenticated_contact(f.phone.credential_id)

        peer = registry.recently_committed_peer(f.phone.credential_id)
        self.assertEqual(peer["credential_id"], f.phone.credential_id)
        self.assertEqual(peer["public_key_der"], f.phone.public_key_der)
