import json
import os
import tempfile
import unittest
import uuid

from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.secure_mode_contract import Binding, ContractMissing, SecureModeContractStore, encode
from openaps_locald.write_challenge import ChallengeError


class SecureModeContractTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="secure-mode-contract-")
        identity_dir = os.path.join(self.root.name, "identity")
        contract_dir = os.path.join(self.root.name, "contract")
        os.mkdir(identity_dir, 0o700); os.mkdir(contract_dir, 0o700)
        self.identity = DeviceIdentity(identity_dir)
        self.storage = AdmissionStorage(contract_dir)
        self.store = SecureModeContractStore(self.storage, self.identity)
        self.binding = Binding("ns_" + "a" * 64, self.identity.credential_id,
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "b" * 64,
            uuid.uuid4(), uuid.uuid4())

    def tearDown(self):
        self.root.cleanup()

    def test_both_processes_consume_one_exact_generation(self):
        generation = uuid.uuid4()
        self.store.issue(self.binding, generation)
        self.assertEqual(self.store.load(self.binding), generation)  # HTTP owner
        self.assertEqual(self.store.load(self.binding), generation)  # BLE owner

    def test_missing_stale_or_process_mismatch_fails_unavailable(self):
        with self.assertRaises(ContractMissing):
            self.store.load(self.binding)
        self.store.issue(self.binding, uuid.uuid4())
        for field in ("settings_epoch", "key_epoch", "policy_generation",
                      "http_instance", "ble_instance"):
            values = self.binding._asdict(); values[field] = uuid.uuid4()
            with self.assertRaises(ChallengeError):
                self.store.load(Binding(**values))

    def test_tamper_and_noncanonical_bytes_fail_closed(self):
        generation = uuid.uuid4(); self.store.issue(self.binding, generation)
        data = self.storage.load(); obj = json.loads(data.decode("utf-8"))
        obj["generation"] = str(uuid.uuid4())
        self.storage.replace(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"), expecting=data)
        with self.assertRaises(ChallengeError):
            self.store.load(self.binding)

    def test_crash_after_prepare_and_interleaved_generation_never_commit(self):
        generation = uuid.uuid4()
        self.store.prepare(self.binding, generation)
        # A new process after a supervisor crash sees prepared, never ready.
        restarted = SecureModeContractStore(self.storage, self.identity)
        with self.assertRaises(ChallengeError): restarted.load(self.binding)
        previous = self.storage.load()
        self.storage.replace(encode(self.binding, uuid.uuid4(), self.identity, "prepared"),
                             expecting=previous)
        with self.assertRaises(ChallengeError): self.store.commit(self.binding, generation)

    def test_commit_treats_post_replace_error_as_success_only_on_exact_readback(self):
        generation = uuid.uuid4()
        self.store.prepare(self.binding, generation)

        class ReportsAfterCommitError(object):
            def __init__(self, inner):
                self.inner = inner
                self.fail_committed = True

            def load(self):
                return self.inner.load()

            def replace(self, data, expecting=None):
                self.inner.replace(data, expecting=expecting)
                if self.fail_committed and json.loads(data.decode("utf-8"))["phase"] == "committed":
                    self.fail_committed = False
                    raise OSError("reported after durable replace")

        recovered = SecureModeContractStore(
            ReportsAfterCommitError(self.storage), self.identity)
        recovered.commit(self.binding, generation)
        self.assertEqual(recovered.load(self.binding), generation)


if __name__ == "__main__":
    unittest.main()
