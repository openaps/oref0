"""Production-shaped admission construction with synthetic proof I/O only."""
import os
import base64
import json
import tempfile
import threading
import unittest
import uuid

from openaps_locald.admission_runtime import AdmissionRuntime
from openaps_locald.authorization_runtime import AuthorizationRuntime
from openaps_locald.reviewed_ingress_policy import ReviewedIngressPolicy
from openaps_locald.write_challenge import ChallengeError
from openaps_locald.reverse_enrollment import BEGIN, READY
from openaps_locald.write_challenge import fresh_challenge, signed_response, response_envelope
from openaps_locald.authorization_tls import TLSError
from openaps_locald.admission_storage import AdmissionStorage
from tests import test_nightscout_write_proof


class AdmissionRuntimeTests(unittest.TestCase):
    def fixture(self):
        f = test_nightscout_write_proof.ProofIOTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        class Anonymous:
            def request_bytes(self, *args, **kwargs):
                return 401, b""
        client = f.client(f.rig, "rig", anonymous_transport=Anonymous())
        f.replies = [(200, b'{"check":true}')]
        observation = client.observe_enrollment_permissions()
        evidence = client.reviewed_policy_evidence(observation)
        root = tempfile.TemporaryDirectory(prefix="openaps-admission-runtime-")
        self.addCleanup(root.cleanup)
        paths = [os.path.join(root.name, name) for name in
                 ("settings-epoch", "key-epoch", "candidates", "committed", "policy-anchor")]
        for path in paths:
            os.mkdir(path, 0o700)
        return f, client, evidence, paths

    def test_complete_factory_is_network_free_and_exposes_both_components(self):
        f, client, evidence, paths = self.fixture()
        count = len(f.calls)
        runtime = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.addCleanup(runtime.invalidate)
        self.assertEqual(len(f.calls), count)
        self.assertTrue(callable(runtime.challenge_publisher))
        self.assertIs(runtime.reverse_workflow, runtime.registry.reverse_workflow)
        self.assertEqual(runtime.settings_store.load_existing(f.rig.credential_id), runtime.registry.scope.settings_epoch)
        self.assertEqual(runtime.key_store.load_existing(f.rig.credential_id), runtime.registry.scope.local_key_generation)

    def test_policy_rejects_booleans_digests_replay_and_foreign_observation(self):
        f, client, evidence, paths = self.fixture()
        for value in (True, "b" * 64, {"denied_known_writes": True}):
            with self.assertRaises(ChallengeError):
                ReviewedIngressPolicy().install(value)
        runtime = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.addCleanup(runtime.invalidate)
        with self.assertRaises(ChallengeError):
            ReviewedIngressPolicy().install(evidence)
        other = f.client(f.phone, "phone", anonymous_transport=client._anonymous)
        f.replies = [(200, b'{"check":true}')]
        observation = client.observe_enrollment_permissions()
        with self.assertRaises(ChallengeError):
            other.reviewed_policy_evidence(observation)

    def test_missing_nonprivate_or_aliased_storage_fails_closed(self):
        f, client, evidence, paths = self.fixture()
        for duplicate in range(1, len(paths)):
            aliased = list(paths)
            aliased[duplicate] = aliased[0]
            with self.assertRaises(ChallengeError):
                AdmissionRuntime(client, f.rig, evidence, *aliased)

    def test_authorization_runtime_exposes_no_partial_components(self):
        f, client, evidence, paths = self.fixture()
        root = os.path.dirname(paths[0])
        runtime = AuthorizationRuntime({"authorization_mode": "legacy",
            "authorization_admission_dir": root})
        runtime.identity, runtime._proof_client = f.rig, client
        self.addCleanup(runtime.close_proof_owner)
        self.assertEqual(runtime.enrollment_components(), (None, None))
        installed = runtime.install_admission_registry(evidence)
        runtime._admission_activation_state = "active"
        publisher, reverse = runtime.enrollment_components()
        self.assertTrue(callable(publisher))
        self.assertIs(reverse, installed.reverse_workflow)
        with self.assertRaises(Exception):
            runtime.install_admission_registry(client.reviewed_policy_evidence(
                self._fresh_observation(f, client)))

    def test_explicit_activation_observes_once_and_publishes_complete_pair(self):
        f, client, _unused_evidence, paths = self.fixture()
        runtime = AuthorizationRuntime({"authorization_mode": "legacy",
            "authorization_admission_dir": os.path.dirname(paths[0])}, enable_admission=True)
        runtime.identity, runtime._proof_client = f.rig, client
        self.addCleanup(runtime.close_proof_owner)
        f.replies = [(200, b'{"check":true}')]
        before = len(f.calls)
        self.assertTrue(runtime._activate_admission_once())
        self.assertEqual(len(f.calls), before + 1)
        self.assertTrue(callable(runtime.tls_stream_factory()))
        publisher, workflow = runtime.enrollment_components()
        self.assertTrue(callable(publisher))
        self.assertIs(workflow, runtime._admission_runtime.reverse_workflow)
        self.assertTrue(runtime._activate_admission_once())
        self.assertEqual(len(f.calls), before + 1)

    def test_production_tls_factory_uses_registry_and_shared_pool(self):
        f, client, evidence, paths = self.fixture()
        runtime = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.addCleanup(runtime.invalidate)
        original = fresh_challenge(f.authority, f.phone.credential_id, "phone",
            f.rig.credential_id, "rig")
        body = {"schema": BEGIN, "challenge": original,
            "phone_public_key_der": base64.b64encode(f.phone.public_key_der).decode("ascii")}
        f.replies = [(200, b'{"check":true}')]
        code, result = runtime.reverse_workflow.handle(body)
        self.assertEqual(code, 200)
        challenge = result["challenge"]
        response = signed_response(challenge, f.phone, f.authority, "phone")
        f.replies = [(200, b"[" + response_envelope(challenge, response, 1000) + b"]"),
                     (200, b'{"check":true}')]
        self.assertEqual(runtime.reverse_workflow.handle(
            {"schema": READY, "nonce": challenge["nonce"]}), (202, None))
        stream = runtime.make_tls_stream(object(), object())
        self.addCleanup(stream.close)
        stream.receive(self._phone_hello(f))
        self.assertIs(stream.session.tls.pool, runtime.admission_pool)
        self.assertTrue(runtime.admission_pool.entries)
        self.assertIsNotNone(runtime.committed_storage.load())
        runtime.invalidate()
        with self.assertRaises(TLSError):
            stream.tick()

    def test_same_scope_registry_reconstruction_requires_explicit_recovery_selection(self):
        f, client, evidence, paths = self.fixture()
        runtime = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.addCleanup(runtime.invalidate)
        self.complete_enrollment(f, runtime)
        self.assertIsNotNone(runtime.committed_storage.load())
        scope, lease = runtime.registry.scope, runtime.registry.policy
        runtime.registry.invalidate()
        from openaps_locald.admission_owner import LiveAdmissionContext
        from openaps_locald.admission_registry import AdmissionRegistry
        from openaps_locald.admission_storage import AdmissionStorage
        reconstructed = AdmissionRegistry(client, f.rig, AdmissionStorage(paths[2]),
            AdmissionStorage(paths[3]), scope, LiveAdmissionContext(scope), lease,
            runtime.registry.validate_persisted, clock=lambda: f.time)
        self.addCleanup(reconstructed.invalidate)
        with self.assertRaises(ChallengeError):
            reconstructed.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        owner, handle = reconstructed.recovery_required(
            f.phone.credential_id, f.phone.public_key_der)
        owner.require_recovery_handle(handle)
        with self.assertRaises(ChallengeError):
            reconstructed._fresh_owner(f.phone.public_key_der)
        with self.assertRaises(ChallengeError):
            reconstructed.snapshot(f.phone.credential_id, str(uuid.uuid4()))

    def test_new_policy_generation_rejects_committed_restore(self):
        f, client, evidence, paths = self.fixture()
        runtime = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.addCleanup(runtime.invalidate)
        self.complete_enrollment(f, runtime)
        f.replies = [(200, b'{"check":true}')]
        observation = client.observe_enrollment_permissions()
        new_policy = ReviewedIngressPolicy()
        new_lease = new_policy.install(client.reviewed_policy_evidence(observation))
        self.addCleanup(new_policy.invalidate)
        from openaps_locald.admission_owner import LiveAdmissionContext
        from openaps_locald.admission_registry import AdmissionRegistry, RegistryScope
        from openaps_locald.admission_storage import AdmissionStorage
        old = runtime.registry.scope
        scope = RegistryScope(old.authority, old.local_credential_id,
            old.settings_epoch, old.local_key_generation, new_lease.generation,
            new_lease.review_sha256)
        def validate(expected):
            self.assertEqual(expected, scope)
            self.assertEqual(runtime.settings_store.load_existing(f.rig.credential_id),
                             expected.settings_epoch)
            self.assertEqual(runtime.key_store.load_existing(f.rig.credential_id),
                             expected.local_key_generation)
        reconstructed = AdmissionRegistry(client, f.rig, AdmissionStorage(paths[2]),
            AdmissionStorage(paths[3]), scope, LiveAdmissionContext(scope), new_lease,
            validate, clock=lambda: f.time)
        self.addCleanup(reconstructed.invalidate)
        with self.assertRaises(ChallengeError):
            reconstructed.recovery_required(f.phone.credential_id, f.phone.public_key_der)

    def test_offline_runtime_restore_is_recovery_only_then_live_upgrade_reuses_generation(self):
        f, client, evidence, paths = self.fixture()
        first = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.complete_enrollment(f, first)
        generation = first.registry.scope.policy_generation
        first.invalidate()
        restored = AdmissionRuntime(client, f.rig, None, *paths, clock=lambda: f.time)
        self.addCleanup(restored.invalidate)
        self.assertEqual(restored.registry.scope.policy_generation, generation)
        with self.assertRaises(ChallengeError):
            restored.registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        with self.assertRaises(ChallengeError):
            restored.registry._fresh_owner(f.phone.public_key_der)
        owner, handle = restored.registry.recovery_required(
            f.phone.credential_id, f.phone.public_key_der)
        owner.require_recovery_handle(handle)
        restored.invalidate()

        upgraded = AdmissionRuntime(client, f.rig, None, *paths, clock=lambda: f.time)
        self.addCleanup(upgraded.invalidate)
        f.replies = [(200, b'{"check":true}')]
        observation = client.observe_enrollment_permissions()
        lease = upgraded.policy_owner.current(f.authority)
        self.assertIs(upgraded.policy_owner.install(
            client.reviewed_policy_evidence(observation), upgraded.policy_binding), lease)
        self.assertEqual(lease.generation, generation)
        owner = upgraded.registry._fresh_owner(f.phone.public_key_der)
        self.assertIsNotNone(owner)

    def test_authorization_runtime_restores_before_network_then_upgrades_same_owner(self):
        f, client, evidence, paths = self.fixture()
        first = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.complete_enrollment(f, first)
        generation = first.registry.scope.policy_generation
        first.invalidate()
        runtime = AuthorizationRuntime({"authorization_mode": "legacy",
            "authorization_admission_dir": os.path.dirname(paths[0])}, enable_admission=True)
        runtime.identity, runtime._proof_client = f.rig, client
        self.addCleanup(runtime.close_proof_owner)
        f.replies = [(503, b"")]
        self.assertFalse(runtime._activate_admission_once())
        recovered = runtime._admission_runtime
        self.assertIsNotNone(runtime.recovery_registry())
        self.assertEqual(runtime.admission_availability()["state"], "recovery_only")
        self.assertEqual(recovered.registry.scope.policy_generation, generation)
        self.assertEqual(runtime.enrollment_components(), (None, None))
        self.assertIsNone(runtime.tls_stream_factory())
        f.replies = [(200, b'{"check":true}')]
        self.assertTrue(runtime._activate_admission_once())
        self.assertIs(runtime._admission_runtime, recovered)
        self.assertEqual(runtime._admission_runtime.registry.scope.policy_generation, generation)
        self.assertTrue(callable(runtime.enrollment_components()[0]))
        self.assertTrue(callable(runtime.tls_stream_factory()))

    def test_authorization_runtime_authoritative_missing_anchor_allows_first_live_install(self):
        f, client, _evidence, paths = self.fixture()
        runtime = AuthorizationRuntime({"authorization_mode": "legacy",
            "authorization_admission_dir": os.path.dirname(paths[0])}, enable_admission=True)
        runtime.identity, runtime._proof_client = f.rig, client
        self.addCleanup(runtime.close_proof_owner)
        f.replies = [(200, b'{"check":true}')]
        self.assertTrue(runtime._activate_admission_once())
        self.assertEqual(runtime.admission_availability()["state"], "active")
        self.assertIsNotNone(AdmissionStorage(paths[4]).load())

    def test_authorization_runtime_malformed_anchor_is_sticky_without_network(self):
        f, client, _evidence, paths = self.fixture()
        AdmissionStorage(paths[4]).replace(b"{}", expecting=None)
        runtime = AuthorizationRuntime({"authorization_mode": "legacy",
            "authorization_admission_dir": os.path.dirname(paths[0])}, enable_admission=True)
        runtime.identity, runtime._proof_client = f.rig, client
        self.addCleanup(runtime.close_proof_owner)
        before = len(f.calls)
        self.assertFalse(runtime._activate_admission_once())
        self.assertEqual(len(f.calls), before)
        self.assertEqual(runtime.admission_availability()["state"], "failed")
        self.assertIsNone(runtime.recovery_registry())
        self.assertFalse(runtime._activate_admission_once())
        self.assertEqual(len(f.calls), before)

    def test_authorization_runtime_changed_settings_epoch_rejects_anchor_before_network(self):
        f, client, evidence, paths = self.fixture()
        first = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        first.invalidate()
        storage = AdmissionStorage(paths[0])
        previous = storage.load()
        changed = json.dumps({"schema": "openaps.key-epoch.v1",
            "key_credential_id": f.rig.credential_id, "epoch": str(uuid.uuid4())},
            sort_keys=True, separators=(",", ":")).encode("utf-8")
        storage.replace(changed, expecting=previous)
        runtime = AuthorizationRuntime({"authorization_mode": "legacy",
            "authorization_admission_dir": os.path.dirname(paths[0])}, enable_admission=True)
        runtime.identity, runtime._proof_client = f.rig, client
        self.addCleanup(runtime.close_proof_owner)
        before = len(f.calls)
        self.assertFalse(runtime._activate_admission_once())
        self.assertEqual(len(f.calls), before)
        self.assertEqual(runtime.admission_availability()["state"], "failed")

    def complete_enrollment(self, f, runtime):
        original = fresh_challenge(f.authority, f.phone.credential_id, "phone",
            f.rig.credential_id, "rig")
        body = {"schema": BEGIN, "challenge": original,
            "phone_public_key_der": base64.b64encode(f.phone.public_key_der).decode("ascii")}
        f.replies = [(200, b'{"check":true}')]
        code, result = runtime.reverse_workflow.handle(body)
        self.assertEqual(code, 200)
        challenge = result["challenge"]
        response = signed_response(challenge, f.phone, f.authority, "phone")
        f.replies = [(200, b"[" + response_envelope(challenge, response, 1000) + b"]"),
                     (200, b'{"check":true}')]
        self.assertEqual(runtime.reverse_workflow.handle(
            {"schema": READY, "nonce": challenge["nonce"]}), (202, None))

    @staticmethod
    def _phone_hello(f):
        from tests.test_authorization_tls import TLSReceiverTests
        fixture = TLSReceiverTests()
        fixture.phone, fixture.rig, fixture.directory = f.phone, f.rig, f.directory
        return fixture.certificate(f.phone, 1).encode()

    def test_activation_is_default_off_and_failure_stays_fail_closed(self):
        class Client:
            observations = 0
            def observe_enrollment_permissions(self):
                self.observations += 1
                return object()
            def reviewed_policy_evidence(self, observation):
                raise ChallengeError("synthetic inconclusive policy")
        client = Client()
        runtime = AuthorizationRuntime({"authorization_mode": "legacy"})
        runtime.identity, runtime._proof_client = object(), client
        self.assertFalse(runtime._activate_admission_once())
        self.assertEqual(client.observations, 0)
        self.assertEqual(runtime.enrollment_components(), (None, None))
        self.assertIsNone(runtime.tls_stream_factory())

        enabled = AuthorizationRuntime({"authorization_mode": "legacy"}, enable_admission=True)
        enabled.identity, enabled._proof_client = object(), client
        self.assertFalse(enabled._activate_admission_once())
        self.assertEqual(client.observations, 1)
        self.assertEqual(enabled._admission_activation_state, "failed")
        self.assertEqual(enabled.enrollment_components(), (None, None))
        self.assertIsNone(enabled.tls_stream_factory())
        self.assertFalse(enabled._activate_admission_once())
        self.assertEqual(client.observations, 1)

    def test_close_racing_observation_cancels_without_installing(self):
        entered, release = threading.Event(), threading.Event()
        class Client:
            invalidated = 0
            def observe_enrollment_permissions(self):
                entered.set()
                release.wait(2)
                return object()
            def reviewed_policy_evidence(self, observation):
                return object()
            def invalidate(self):
                self.invalidated += 1
            def reap_cancelled_network_worker(self):
                return True
        client = Client()
        runtime = AuthorizationRuntime({"authorization_mode": "legacy"}, enable_admission=True)
        runtime.identity, runtime._proof_client = object(), client
        result = []
        thread = threading.Thread(target=lambda: result.append(runtime._activate_admission_once()))
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertTrue(runtime.close_proof_owner())
        release.set()
        thread.join(2)
        self.assertEqual(result, [False])
        self.assertEqual(client.invalidated, 1)
        self.assertEqual(runtime._admission_activation_state, "cancelled")
        self.assertEqual(runtime.enrollment_components(), (None, None))
        self.assertIsNone(runtime.tls_stream_factory())

    @staticmethod
    def _fresh_observation(f, client):
        f.replies = [(200, b'{"check":true}')]
        return client.observe_enrollment_permissions()
