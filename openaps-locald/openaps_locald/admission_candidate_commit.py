"""Guarded candidate CAS persistence, not admission activation.

The caller supplies a SEPARATE store (e.g. AdmissionStorage in a dedicated
candidate directory), never the proof archive's store. Its context guard must
hold settings/key/policy generations stable for the entire synchronous block.
A test-injected guard is not a production reviewed-ingress capability.
"""
import threading

from . import admission_record
from .admission_candidate_archive import CandidateArchive
from .write_challenge import ChallengeError


class CandidateCommitCoordinator:
    def __init__(self, client, candidate_storage, context, verifier_identity, context_guard):
        self._client, self._storage = client, candidate_storage
        self._context, self._identity, self._guard = context, verifier_identity, context_guard
        self._operation = threading.Lock()
        self._cancelled = threading.Event()

    def invalidate(self):
        self._cancelled.set()

    def _check(self, receipt, before, after):
        if self._cancelled.is_set():
            raise ChallengeError("candidate commit invalidated")
        self._client.validate_observed_readback(receipt, before, after)
        if self._cancelled.is_set():
            raise ChallengeError("candidate commit invalidated")

    def commit_candidate(self, receipt, before, after):
        if not self._operation.acquire(False):
            raise ChallengeError("candidate commit busy")
        try:
            with self._guard(self._context):
                self._check(receipt, before, after)
            previous = self._storage.load()
            archive = CandidateArchive(previous)  # Reject proof archives instead of overwriting them.
            candidate = admission_record.prepare(self._client, receipt, before, after, self._context, self._identity)
            encoded = archive.inserting(candidate, self._identity).encoded()
            with self._guard(self._context):
                self._check(receipt, before, after)
                self._storage.replace(encoded, expecting=previous)
                # An exception after replacement is ambiguous. Never return a
                # candidate as committed and never claim rollback in that case.
                self._check(receipt, before, after)
            return candidate
        finally:
            self._operation.release()
