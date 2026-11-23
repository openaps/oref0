import contextlib
import os
import tempfile
import unittest

from openaps_locald.admission_candidate_archive import CandidateArchive
from openaps_locald.admission_candidate_commit import CandidateCommitCoordinator
from openaps_locald.admission_storage import AdmissionStorage, StorageError
from openaps_locald.proof_archive import ProofArchive
from openaps_locald.write_challenge import ChallengeError
from tests import test_admission_record


class CandidateCommitTests(unittest.TestCase):
    def fixture(self):
        value = test_admission_record.AdmissionRecordTests()
        value.setUp()
        self.addCleanup(value.doCleanups)
        return value

    @contextlib.contextmanager
    def synthetic_guard(self, context):
        # Fixture only. No deployment policy review is implied.
        yield

    def owner(self, f, storage, guard=None):
        return CandidateCommitCoordinator(f.client, storage, f.context, f.fixture.phone,
            guard or self.synthetic_guard)

    def commit(self, owner, f):
        return owner.commit_candidate(f.receipt, f.before, f.after)

    def test_private_storage_retains_other_peer_context(self):
        first, second = self.fixture(), self.fixture()
        directory = tempfile.TemporaryDirectory(prefix="openaps-candidate-store-")
        self.addCleanup(directory.cleanup)
        os.chmod(directory.name, 0o700)
        store = AdmissionStorage(directory.name)  # Dedicated synthetic candidate store.
        a = self.commit(self.owner(first, store), first)
        b = self.commit(self.owner(second, store), second)
        restored = CandidateArchive(store.load())
        self.assertEqual(restored.count, 2)
        self.assertEqual(restored.candidate(first.context, first.fixture.phone).commit_id, a.commit_id)
        self.assertEqual(restored.candidate(second.context, second.fixture.phone).commit_id, b.commit_id)

    def test_stale_context_expiry_cas_invalidation_and_write_ambiguity(self):
        for mode in ("context", "expiry", "cas", "invalidate", "write_ambiguity", "proof_archive"):
            f = self.fixture()
            class Store:
                value = ProofArchive().encoded() if mode == "proof_archive" else None
                writes = 0
                def load(self):
                    previous = self.value
                    if mode == "cas":
                        self.value = CandidateArchive().encoded()
                    if mode == "expiry":
                        f.fixture.time = 120.0
                    if mode == "invalidate":
                        owner.invalidate()
                    return previous
                def replace(self, data, expecting):
                    if self.value != expecting:
                        raise StorageError("synthetic conflict")
                    self.value = data
                    self.writes += 1
                    if mode == "write_ambiguity":
                        raise StorageError("synthetic acknowledged-state uncertainty")
            store = Store()
            calls = [0]
            @contextlib.contextmanager
            def guard(context):
                calls[0] += 1
                if mode == "context" and calls[0] == 2:
                    raise ChallengeError("synthetic changed context")
                yield
            owner = self.owner(f, store, guard)
            with self.assertRaises((ChallengeError, StorageError), msg=mode):
                self.commit(owner, f)
            self.assertEqual(store.writes, 1 if mode == "write_ambiguity" else 0, mode)
            if mode == "write_ambiguity":
                self.assertEqual(CandidateArchive(store.value).count, 1)  # Error never promises rollback.

    def test_archive_rejects_duplicate_oversized_and_proof_schema(self):
        from openaps_locald.admission_candidate_archive import MAX_BYTES
        valid = CandidateArchive().encoded()
        for invalid in (b"", b" " * (MAX_BYTES + 1), ProofArchive().encoded(),
                b'{"schema":"duplicate",' + valid[1:]):
            with self.assertRaises(ChallengeError):
                CandidateArchive(invalid)
