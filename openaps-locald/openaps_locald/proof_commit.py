"""Joined proof-to-audit persistence, never active admission or TLS trust.

The review digest is an audit reference, not reviewed ingress evidence. Runtime
configuration/key/policy generations and continuity/restore remain separate.
"""
import threading

from . import stored_proof
from .proof_archive import ProofArchive
from .write_challenge import ChallengeError


class ProofCommitCoordinator:
    def __init__(self, client, storage, review_sha256, verifier_identity):
        self._client = client
        self._storage = storage
        self._review = review_sha256
        self._identity = verifier_identity
        self._operation = threading.Lock()
        self._cancelled = threading.Event()

    def invalidate(self):
        self._cancelled.set()
        self._client.invalidate()

    def _check(self):
        if self._cancelled.is_set():
            raise ChallengeError("audit commit invalidated")

    def commit_audit(self, receipt, before, after):
        if not self._operation.acquire(False):
            raise ChallengeError("audit commit busy")
        try:
            self._check()
            self._client.validate_observed_readback(receipt, before, after)
            self._check()
            previous = self._storage.load()
            archive = ProofArchive(previous)
            encoded = stored_proof.encode(receipt, self._review, self._identity)
            fields = receipt.challenge
            proof = stored_proof.decode(encoded, fields["authority_context_id"],
                fields["verifier_credential_id"], fields["verifier_device_kind"],
                fields["peer_credential_id"], self._review, self._identity)
            candidate = archive.inserting(proof, self._identity).encoded()
            self._client.validate_observed_readback(receipt, before, after)
            self._check()
            self._storage.replace(candidate, expecting=previous)
            # Cancellation during storage is ambiguous; this is never a trust
            # activation and neither cancellation nor error promises rollback.
            self._check()
        finally:
            self._operation.release()
