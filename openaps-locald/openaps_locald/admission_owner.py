"""Fresh-only rig admission ownership, never activation from restored bytes.

Runtime must own/invalidate LiveAdmissionContext before settings/key replacement.
It contains no persistent epoch I/O: commit callers supply the already captured
exact context; persistent epoch validation is separately supplied at publication.
"""
import contextlib
import threading
import uuid

from .admission_candidate_commit import CandidateCommitCoordinator
from .authorization_tls import boottime
from .continuity import BoundContinuity, Continuity, ContinuityError
from .reviewed_ingress_policy import _Lease
from .write_challenge import ChallengeError
from . import committed_admission
from .recovery_exchange import RecoveryExchange
from .recovery_tls_client import RecoveryTLSClient


_HANDLE_TOKEN = object()


class _RecoveryRequired:
    """Owner-local restricted state, never a deserialized capability."""
    def __init__(self, token, owner, generation, audit):
        if token is not _HANDLE_TOKEN:
            raise ChallengeError("owner-issued recovery handle required")
        self._owner, self._generation, self._audit = owner, generation, audit


class _RecoveryAttempt:
    def __init__(self, token, owner, handle, connection, exchange):
        if token is not _HANDLE_TOKEN:
            raise ChallengeError("owner-issued recovery attempt required")
        self._owner, self._handle, self.connection, self.exchange = owner, handle, connection, exchange

    def admission(self):
        return self._owner._recovery_admission(self)


class LiveAdmissionContext:
    def __init__(self, context):
        self._context = context
        self._valid = True
        self._lock = threading.RLock()

    @contextlib.contextmanager
    def hold(self, expected):
        with self._lock:
            if not self._valid or self._context != expected:
                raise ChallengeError("admission context changed")
            yield
            if not self._valid or self._context != expected:
                raise ChallengeError("admission context changed")

    def invalidate(self):
        with self._lock:
            self._valid = False


class _ContextContinuity(BoundContinuity):
    def __init__(self, state, binding, live_context, context, policy):
        super(_ContextContinuity, self).__init__(state, binding)
        self._live_context, self._context = live_context, context
        self._policy = policy
        self._lock = threading.RLock()

    @contextlib.contextmanager
    def _current_context(self):
        try:
            with self._live_context.hold(self._context):
                with self._policy.hold():
                    with self._lock:
                        yield
        except ChallengeError:
            raise ContinuityError("admission context changed") from None

    def require_current(self, binding):
        with self._current_context():
            super(_ContextContinuity, self).require_current(binding)

    def authenticated_direct_contact(self, binding):
        with self._current_context():
            super(_ContextContinuity, self).authenticated_direct_contact(binding)

    def witness_response(self, request, identity, binding):
        with self._current_context():
            return super(_ContextContinuity, self).witness_response(request, identity, binding)

    def invalidate(self):
        with self._lock:
            super(_ContextContinuity, self).invalidate()


class AdmissionOwner:
    def __init__(self, client, candidate_storage, context, identity, live_context, policy,
                 validate_persisted_context, clock=boottime, committed_storage=None):
        if (not isinstance(policy, _Lease) or not isinstance(live_context, LiveAdmissionContext) or
                context.local_kind != "rig" or context.local_credential_id != identity.credential_id or
                context.authority != policy.authority or context.policy_generation != policy.generation or
                context.policy_review_sha256 != policy.review_sha256):
            raise ChallengeError("admission owner context")
        self._context, self._identity, self._live_context, self._policy = context, identity, live_context, policy
        self._validate_persisted = validate_persisted_context
        self._clock = clock
        self._lock = threading.RLock()
        self._operation = threading.Lock()
        self._valid, self._entry = True, None
        if committed_storage is candidate_storage and committed_storage is not None:
            raise ChallengeError("dedicated committed storage required")
        self._committed_storage = committed_storage
        self._recovery_generation, self._recovery_handle = object(), None
        self._attempt = None
        self._active_trust = self._excluded_connection = None
        self._commit = CandidateCommitCoordinator(client, candidate_storage, context, identity, self._guard)
        with self._guard(context):
            pass

    @contextlib.contextmanager
    def _guard(self, context):
        # Uniform order: live settings context -> policy -> published owner.
        with self._live_context.hold(context):
            self._validate_persisted(context)
            with self._policy.hold():
                with self._lock:
                    if not self._valid or self._identity.credential_id != context.local_credential_id:
                        raise ChallengeError("admission owner invalidated")
                    yield
                    if not self._valid:
                        raise ChallengeError("admission owner invalidated")
                self._validate_persisted(context)

    def admit_fresh(self, receipt, before, after):
        self._policy.require_fresh()
        if not self._operation.acquire(False):
            raise ChallengeError("admission owner busy")
        published = None
        committed_started = False
        try:
            with self._lock:
                if self._attempt is not None:
                    self._attempt.exchange.cancel()
                    self._attempt = None
                self._recovery_generation, self._recovery_handle = object(), None
            # Start contact age before preparation/CAS, never after it completes.
            state = Continuity(clock=self._clock)
            candidate = self._commit.commit_candidate(receipt, before, after)
            if self._committed_storage is not None:
                committed_started = True
                self._commit_durable(candidate, receipt, before, after)
            with self._guard(self._context):
                self._commit._check(receipt, before, after)
                state.require_current()
                binding = self._binding("admission", str(candidate.commit_id))
                continuity = _ContextContinuity(state, binding, self._live_context, self._context, self._policy)
                self._policy.register(continuity)
                self._commit._check(receipt, before, after)
                if self._entry is not None:
                    self._entry[1].invalidate()
                self._entry = (candidate, continuity)
                self._active_trust, self._excluded_connection = str(candidate.commit_id), None
                published = continuity
            return candidate.commit_id
        except Exception:
            if committed_started:
                self.invalidate()
            if published is not None:
                with self._lock:
                    published.invalidate()
                    if self._entry is not None and self._entry[1] is published:
                        self._entry = None
            raise
        finally:
            self._operation.release()

    def _commit_durable(self, candidate, receipt, before, after):
        try:
            self._write_durable(candidate, receipt, before, after)
        except Exception:
            # Includes the guard's post-write persisted-scope validation.
            self.invalidate()
            raise

    def _write_durable(self, candidate, receipt, before, after):
        with self._guard(self._context):
            self._commit._check(receipt, before, after)
            previous = self._committed_storage.load()
            archive = committed_admission.CommittedArchive(previous)
            audit = committed_admission.prepare(candidate, self._context, self._identity)
            encoded = archive.inserting(audit, self._context, self._identity).encoded()
            self._commit._check(receipt, before, after)
            try:
                self._committed_storage.replace(encoded, expecting=previous)
                if self._committed_storage.load() != encoded:
                    raise ChallengeError("committed readback mismatch")
                self._commit._check(receipt, before, after)
            except Exception:
                # Durable bytes may already exist. This process cannot activate
                # them or assume rollback; a new owner must require recovery.
                self.invalidate()
                raise

    def restore_recovery_required(self):
        if not self._operation.acquire(False):
            raise ChallengeError("admission owner busy")
        try:
            with self._guard(self._context):
                if self._committed_storage is None or self._entry is not None:
                    raise ChallengeError("restricted restore unavailable")
                data = self._committed_storage.load()
                if data is None:
                    raise ChallengeError("committed admission missing")
                audit = committed_admission.CommittedArchive(data).record(self._context, self._identity)
                if audit is None:
                    raise ChallengeError("exact committed admission missing")
                handle = _RecoveryRequired(_HANDLE_TOKEN, self, object(), audit)
                if self._attempt is not None:
                    self._attempt.exchange.cancel()
                    self._attempt = None
                self._recovery_generation, self._recovery_handle = handle._generation, handle
            return handle
        finally:
            self._operation.release()

    def require_recovery_handle(self, handle):
        """Validate restricted owner membership; grants no TLS/admission data."""
        with self._guard(self._context):
            if (not isinstance(handle, _RecoveryRequired) or handle is not self._recovery_handle or
                    handle._owner is not self or handle._generation is not self._recovery_generation or
                    self._entry is not None):
                raise ChallengeError("stale recovery handle")

    def begin_recovery(self, handle, connection):
        with self._guard(self._context):
            self.require_recovery_handle(handle)
            try:
                if not isinstance(connection, str) or str(uuid.UUID(connection)) != connection:
                    raise ValueError()
            except ValueError:
                raise ChallengeError("canonical recovery connection required") from None
            if self._attempt is not None:
                raise ChallengeError("recovery attempt already active")
            exchange = RecoveryExchange(self._context.authority, self._context.local_credential_id,
                "rig", self._context.peer_credential_id, "phone", handle._audit.candidate.proof.public_key_der,
                connection, self._identity, clock=self._clock)
            attempt = _RecoveryAttempt(_HANDLE_TOKEN, self, handle, connection, exchange)
            self._attempt = attempt
            return attempt

    def _require_attempt(self, attempt):
        if (type(attempt) is not _RecoveryAttempt or attempt is not self._attempt or
                attempt._owner is not self):
            raise ChallengeError("stale recovery attempt")
        self.require_recovery_handle(attempt._handle)

    def _recovery_admission(self, attempt):
        with self._guard(self._context):
            self._require_attempt(attempt)
            audit = attempt._handle._audit
            trust = audit.recovery.recovery_commit_id if audit.recovery else audit.commit_id
            return dict(zip(("authority_context_id", "local_credential_id", "peer_credential_id",
                "connection_generation", "trust_generation"), self._binding(attempt.connection, str(trust))),
                peer={"credential_id": self._context.peer_credential_id,
                      "public_key_der": audit.candidate.proof.public_key_der, "device_kind": "phone",
                      "authority_context_id": self._context.authority})

    def cancel_recovery(self, attempt):
        with self._lock:
            if attempt is self._attempt:
                self._attempt = None
                attempt.exchange.cancel()

    def commit_recovery(self, attempt, engine, completion):
        if not self._operation.acquire(False):
            raise ChallengeError("admission owner busy")
        writing = False
        try:
            with self._guard(self._context):
                self._require_attempt(attempt)
                if type(engine) is not RecoveryTLSClient or engine.exchange is not attempt.exchange:
                    raise ChallengeError("exact recovery engine required")
                engine.require_completion(completion)
                if engine.binding != tuple(self._recovery_admission(attempt)[k] for k in
                        ("authority_context_id", "local_credential_id", "peer_credential_id",
                         "connection_generation", "trust_generation")):
                    raise ChallengeError("recovery engine binding")
                evidence = engine._evidence
                attempt.exchange.current_contact_age(evidence)
                previous = self._committed_storage.load()
                archive = committed_admission.CommittedArchive(previous)
                stored = archive.record(self._context, self._identity)
                if stored is None or stored.encoded != attempt._handle._audit.encoded:
                    raise ChallengeError("recovery base replaced")
                revised = committed_admission.prepare_recovery(stored, self._context, self._identity,
                                                              attempt.exchange, evidence)
                encoded = archive.inserting(revised, self._context, self._identity).encoded()
                engine.require_completion(completion)
                attempt.exchange.current_contact_age(evidence)
                writing = True
                self._committed_storage.replace(encoded, expecting=previous)
                if self._committed_storage.load() != encoded:
                    raise ChallengeError("recovery readback mismatch")
                attempt.exchange.current_contact_age(evidence)
            with self._guard(self._context):
                self._require_attempt(attempt)
                engine.require_completion(completion)
                anchor = self._clock()
                age = attempt.exchange.current_contact_age(evidence)
                first_sample = [True]
                def anchored_clock():
                    if first_sample[0]:
                        first_sample[0] = False
                        return anchor
                    return self._clock()
                state = Continuity(clock=anchored_clock, recovered_age=age)
                trust = str(revised.recovery.recovery_commit_id)
                continuity = _ContextContinuity(state, self._binding("admission", trust),
                    self._live_context, self._context, self._policy)
                self._policy.register(continuity)
                attempt.exchange.current_contact_age(evidence)
                state.require_current()
                attempt.exchange.current_contact_age(evidence)
                if self._attempt is not attempt or not self._valid:
                    raise ChallengeError("recovery cancelled before publication")
                self._entry = (revised.candidate, continuity)
                self._active_trust, self._excluded_connection = trust, attempt.connection
                self._attempt = None
                self._recovery_handle, self._recovery_generation = None, object()
            attempt.exchange.current_contact_age(evidence)
            state.require_current()
            attempt.exchange.cancel()
            return revised.recovery.recovery_commit_id
        except Exception:
            if writing:
                self.invalidate()
            else:
                self.cancel_recovery(attempt)
            raise
        finally:
            self._operation.release()

    def validate_enrollment_context(self, client, authority, local_credential_id, peer_credential_id,
                                    require_unadmitted=False):
        """Verify the exact live owner before proof I/O; returns no admission."""
        with self._guard(self._context):
            if (client is not self._commit._client or self._context.authority != authority or
                    self._context.local_credential_id != local_credential_id or
                    self._context.peer_credential_id != peer_credential_id):
                raise ChallengeError("enrollment owner mismatch")
            if require_unadmitted and self._entry is not None:
                raise ChallengeError("fresh enrollment attempt owner required")

    def _binding(self, connection, trust):
        return (self._context.authority, self._context.local_credential_id,
            self._context.peer_credential_id, connection, trust)

    def snapshot(self, connection):
        # No persistent store/keychain/network reads on the transport path.
        try:
            if not isinstance(connection, str) or str(uuid.UUID(connection)) != connection:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ChallengeError("canonical connection UUID required") from None
        with self._live_context.hold(self._context):
            with self._policy.hold():
                with self._lock:
                    if not self._valid or self._entry is None:
                        raise ChallengeError("admission unavailable")
                    if connection == self._excluded_connection:
                        raise ChallengeError("recovery connection cannot become normal")
                    candidate, continuity = self._entry
                    binding = self._binding(connection, self._active_trust)
                    continuity.require_current(binding)
                    return dict(zip(("authority_context_id", "local_credential_id", "peer_credential_id",
                        "connection_generation", "trust_generation"), binding), continuity=continuity, peer={
                        "credential_id": self._context.peer_credential_id, "public_key_der": candidate.proof.public_key_der,
                        "device_kind": "phone", "authority_context_id": self._context.authority})

    def invalidate(self):
        with self._lock:
            self._valid = False
            if self._attempt is not None:
                self._attempt.exchange.cancel()
                self._attempt = None
            self._recovery_generation, self._recovery_handle = object(), None
            if self._entry is not None:
                self._entry[1].invalidate()
                self._entry = None
        self._commit.invalidate()
