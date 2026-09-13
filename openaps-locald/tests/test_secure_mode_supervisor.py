import os
import tempfile
import unittest
import uuid

from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.secure_mode_contract import SecureModeContractStore
from openaps_locald.secure_mode_supervisor import Scope, SecureModeSupervisor
from openaps_locald.write_challenge import ChallengeError


class SecureModeSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="secure-mode-supervisor-")
        identity = os.path.join(self.root.name, "identity"); contract = os.path.join(self.root.name, "contract")
        os.mkdir(identity, 0o700); os.mkdir(contract, 0o700)
        self.identity = DeviceIdentity(identity)
        self.store = SecureModeContractStore(AdmissionStorage(contract), self.identity)
        self.scope = Scope("ns_" + "a" * 64, self.identity.credential_id,
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "b" * 64)

    def tearDown(self): self.root.cleanup()

    def owner(self, role, instance=None, scope=None, fail=False, calls=None):
        calls = calls if calls is not None else []
        return (role, instance or uuid.uuid4(), scope or self.scope,
                lambda generation, binding: (_ for _ in ()).throw(ValueError("fail")) if fail else calls.append(("arm", role)),
                lambda generation, binding: calls.append(("abort", role)))

    def test_default_off_and_incomplete_reports_never_prepare(self):
        with self.assertRaises(ChallengeError):
            SecureModeSupervisor(self.store).report(*self.owner("http"))
        supervisor = SecureModeSupervisor(self.store, enabled=True)
        supervisor.report(*self.owner("http"))
        with self.assertRaises(ChallengeError): supervisor.coordinate()
        self.assertIsNone(self.store.storage.load())

    def test_both_arm_before_one_committed_generation_is_visible(self):
        calls = []; supervisor = SecureModeSupervisor(self.store, enabled=True)
        def report(role):
            instance = uuid.uuid4()
            def arm(generation, binding):
                with self.assertRaises(ChallengeError): self.store.load(binding)
                calls.append(("arm", role))
            return role, instance, self.scope, arm, lambda generation, binding: calls.append(("abort", role))
        supervisor.report(*report("http")); supervisor.report(*report("ble"))
        generation, binding = supervisor.coordinate()
        self.assertEqual(calls, [("arm", "http"), ("arm", "ble")])
        self.assertEqual(self.store.load(binding), generation)

    def test_second_owner_failure_aborts_first_and_never_commits(self):
        calls = []; supervisor = SecureModeSupervisor(self.store, enabled=True)
        supervisor.report(*self.owner("http", calls=calls))
        supervisor.report(*self.owner("ble", fail=True, calls=calls))
        with self.assertRaises(ChallengeError): supervisor.coordinate()
        self.assertEqual(calls, [("arm", "http"), ("abort", "http")])
        with self.assertRaises(ChallengeError):
            self.store.load(self._binding_from(supervisor))

    def _binding_from(self, supervisor):
        http, ble = supervisor.reports["http"], supervisor.reports["ble"]
        return __import__("openaps_locald.secure_mode_contract", fromlist=["Binding"]).Binding(
            *(tuple(http.scope) + (http.instance, ble.instance)))

    def test_stale_or_mismatched_instances_and_scope_reject_before_write(self):
        for mismatch in ("instance", "scope"):
            supervisor = SecureModeSupervisor(self.store, enabled=True)
            shared = uuid.uuid4()
            supervisor.report(*self.owner("http", instance=shared))
            other_scope = self.scope._replace(policy_generation=uuid.uuid4())
            supervisor.report(*self.owner("ble", instance=shared if mismatch == "instance" else None,
                                          scope=other_scope if mismatch == "scope" else None))
            with self.assertRaises(ChallengeError): supervisor.coordinate()
            self.assertIsNone(self.store.storage.load())


if __name__ == "__main__": unittest.main()
