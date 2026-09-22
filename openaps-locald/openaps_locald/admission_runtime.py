"""Fail-closed construction of a startup-owned admission registry."""
import os
import threading
import uuid

from .admission_owner import LiveAdmissionContext
from .admission_registry import AdmissionRegistry, RegistryScope
from .admission_storage import AdmissionStorage
from .key_epoch import KeyEpochStore
from .reviewed_ingress_policy import ReviewedIngressPolicy
from .reviewed_ingress_policy import _review_sha256
from .reviewed_policy_anchor import Binding, PolicyAnchorStore
from .write_challenge import ChallengeError
from .authorization_tls import AdmissionPool, CertificateHello, LocalCertificateStore, TLSServer, boottime
from .tls_clinical import TLSClinicalSession
from .tls_stream import TLSStream
from .recovery_tls import RecoveryHello
from .recovery_stream import RecoveryStream
from .recovery_witness_stream import RecoveryWitnessStream
from . import recovery_http_prelude


class AdmissionRuntime:
    def __init__(self, proof_client, identity, evidence, settings_directory,
                 key_directory, candidate_directory, committed_directory,
                 policy_anchor_directory, clock=None):
        directories = (settings_directory, key_directory, candidate_directory,
                       committed_directory, policy_anchor_directory)
        if (proof_client is None or identity is None or
                any(not isinstance(path, str) or not os.path.isabs(path) for path in directories) or
                len(set(directories)) != len(directories)):
            raise ChallengeError("distinct absolute admission storage required")
        settings_store = KeyEpochStore(AdmissionStorage(settings_directory))
        key_store = KeyEpochStore(AdmissionStorage(key_directory))
        settings_epoch = settings_store.bootstrap_fresh_enrollment(identity.credential_id)
        key_epoch = key_store.bootstrap_fresh_enrollment(identity.credential_id)
        anchor_store = PolicyAnchorStore(AdmissionStorage(policy_anchor_directory), identity)
        review = _review_sha256(proof_client.authority_context_id)
        policy_binding = Binding(proof_client.authority_context_id, identity.credential_id,
            "rig", settings_epoch, key_epoch, review)
        policy_owner = ReviewedIngressPolicy(anchor_store)
        lease = (policy_owner.restore(policy_binding) if evidence is None else
                 policy_owner.install(evidence, policy_binding))
        scope = RegistryScope(lease.authority, identity.credential_id, settings_epoch,
            key_epoch, lease.generation, lease.review_sha256)
        live = LiveAdmissionContext(scope)

        def validate(expected):
            if expected != scope:
                raise ChallengeError("admission runtime scope changed")
            if settings_store.load_existing(identity.credential_id) != settings_epoch:
                raise ChallengeError("settings epoch changed")
            if key_store.load_existing(identity.credential_id) != key_epoch:
                raise ChallengeError("key epoch changed")

        self.clock = clock or boottime
        kwargs = {"clock": self.clock}
        candidate_storage = AdmissionStorage(candidate_directory)
        committed_storage = AdmissionStorage(committed_directory)
        registry = AdmissionRegistry(proof_client, identity, candidate_storage,
            committed_storage, scope, live, lease, validate, **kwargs)
        certificate_store = LocalCertificateStore(**kwargs)
        local_hello = certificate_store.get(identity)
        admission_pool = AdmissionPool(**kwargs)
        self.policy_owner, self.live_context = policy_owner, live
        self.policy_anchor_store, self.policy_binding = anchor_store, policy_binding
        self.settings_store, self.key_store = settings_store, key_store
        self.candidate_storage, self.committed_storage = candidate_storage, committed_storage
        self.registry = registry
        self.certificate_store, self.local_hello = certificate_store, local_hello
        self.admission_pool = admission_pool
        self._recovery_preludes = {}
        self._recovery_prelude_lock = threading.Lock()

    @property
    def challenge_publisher(self):
        return self.registry.client.publish_own_response

    @property
    def reverse_workflow(self):
        return self.registry.reverse_workflow

    def upgrade_policy(self, evidence):
        """Consume live evidence into this exact restored owner/generation."""
        lease = self.policy_owner.current(self.policy_binding.authority)
        if self.policy_owner.install(evidence, self.policy_binding) is not lease:
            raise ChallengeError("policy lease replaced")
        if self.registry.scope.policy_generation != lease.generation:
            raise ChallengeError("policy generation changed")
        lease.require_fresh()

    def make_tls_stream(self, events, reads):
        """Create one HTTP-owned stream; trust comes only from this registry."""
        local_hello, pool, registry, identity = (
            self.local_hello, self.admission_pool, self.registry, self.registry.identity)
        def session(peer_frame, token):
            peer = CertificateHello.decode(peer_frame, openssl_path=identity.openssl_path,
                lock_path=identity.openssl_lock_path)
            provider = registry.provider(peer.credential_id, str(uuid.uuid4()))
            tls = TLSServer(identity, local_hello, peer_frame, provider,
                clock=self.clock, admission=pool, admission_token=token)
            return TLSClinicalSession(
                tls,
                events,
                reads,
                authenticated_contact=lambda: registry.record_authenticated_contact(
                    peer.credential_id
                ),
            )
        return TLSStream(local_hello, session, pool, clock=self.clock)

    def make_recovery_stream(self, peer_credential_id, peer_public_key_der):
        """Internal restricted requester; no clinical callbacks or route."""
        hello = RecoveryHello(2, self.local_hello.der,
            openssl_path=self.registry.identity.openssl_path,
            lock_path=self.registry.identity.openssl_lock_path)
        return RecoveryStream(self.registry, self.registry.identity, hello,
            self.admission_pool, peer_credential_id, peer_public_key_der, self.clock)

    def make_recovery_witness_stream(self, peer_credential_id, peer_public_key_der):
        """Create a rig-witness stream for an exact active phone admission."""
        hello = RecoveryHello(2, self.local_hello.der,
            openssl_path=self.registry.identity.openssl_path,
            lock_path=self.registry.identity.openssl_lock_path)
        return RecoveryWitnessStream(self.registry, self.registry.identity, hello,
            self.admission_pool, peer_credential_id, peer_public_key_der, self.clock)

    def make_recovery_stream_from_prelude(self, data):
        """Authenticate a bounded selector against the exact committed peer."""
        fields, key, _signature = recovery_http_prelude.shape(data)
        peer = fields["requester_credential_id"]
        stream = self.make_recovery_stream(peer, key)
        try:
            nonce = recovery_http_prelude.verify(data, self.registry.identity,
                self.registry.scope.authority, self.registry.identity.credential_id,
                peer, key)
            with self._recovery_prelude_lock:
                now = self.clock()
                for expired in [value for value, started in self._recovery_preludes.items()
                                if now - started >= 20]:
                    self._recovery_preludes.pop(expired, None)
                if nonce in self._recovery_preludes or len(self._recovery_preludes) >= 128:
                    raise ChallengeError("recovery prelude replay or capacity")
                self._recovery_preludes[nonce] = now
            return stream
        except Exception:
            try:
                stream.transport_terminated()
            except Exception:
                pass
            raise

    def make_recovery_witness_stream_from_prelude(self, data):
        """Create the HTTP route's phone-requester/rig-witness stream."""
        fields, key, _signature = recovery_http_prelude.shape(data)
        peer = fields["requester_credential_id"]
        nonce = recovery_http_prelude.verify(data, self.registry.identity,
            self.registry.scope.authority, self.registry.identity.credential_id,
            peer, key)
        with self._recovery_prelude_lock:
            now = self.clock()
            for expired in [value for value, started in self._recovery_preludes.items()
                            if now - started >= 20]:
                self._recovery_preludes.pop(expired, None)
            if nonce in self._recovery_preludes or len(self._recovery_preludes) >= 128:
                raise ChallengeError("recovery prelude replay or capacity")
            self._recovery_preludes[nonce] = now
        try:
            return self.make_recovery_witness_stream(peer, key)
        except Exception:
            with self._recovery_prelude_lock:
                self._recovery_preludes.pop(nonce, None)
            raise

    def invalidate(self):
        self.live_context.invalidate()
        self.policy_owner.invalidate()
        self.registry.invalidate()
