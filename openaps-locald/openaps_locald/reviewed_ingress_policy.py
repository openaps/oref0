"""Typed live reviewed-policy ownership; production begins unavailable.

There is no digest/Boolean installation API. Actual deployment evidence
installation remains required. Tests construct synthetic fixtures in test code.
"""
import contextlib
import threading
import weakref
import hashlib
import uuid

from .write_challenge import ChallengeError


def _review_sha256(authority):
    statement = ("openaps.reviewed-ingress-policy.v1\0" + authority
        + "\0api:devicestatus:read=true"
        + "\0api:devicestatus:create=false"
        + "\0api:*:create,update,delete=false"
        + "\0assumption=stable-during-bounded-proof")
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()


class _LiveClientEvidence:
    """Opaque, single-use evidence minted and revalidated by one live proof client."""
    def __init__(self, client, observation):
        self._client = weakref.ref(client)
        self._observation = observation
        self._used = False
        self._lock = threading.Lock()

    def claim(self):
        with self._lock:
            if self._used:
                raise ChallengeError("review evidence already consumed")
            client = self._client()
            if client is None:
                raise ChallengeError("review evidence owner unavailable")
            authority = client._validate_reviewed_policy_evidence(self._observation)
            self._used = True
            return authority


def _mint_live_client_evidence(client, observation):
    return _LiveClientEvidence(client, observation)


class _Lease:
    def __init__(self, owner, authority, generation, review, fresh=True):
        self._owner = weakref.ref(owner)
        self._authority, self._generation, self._review = authority, generation, review
        self._fresh = fresh is True

    authority = property(lambda self: self._authority)
    generation = property(lambda self: self._generation)
    review_sha256 = property(lambda self: self._review)

    @contextlib.contextmanager
    def hold(self):
        owner = self._owner()
        if owner is None:
            raise ChallengeError("reviewed policy unavailable")
        with owner._lock:
            if owner._lease is not self:
                raise ChallengeError("reviewed policy unavailable")
            yield
            if owner._lease is not self:
                raise ChallengeError("reviewed policy changed")

    def require_fresh(self):
        with self.hold():
            if not self._fresh:
                raise ChallengeError("fresh reviewed-policy evidence required")

    def register(self, continuity):
        with self.hold():
            owner = self._owner()
            owner._continuities = [value for value in owner._continuities if value() is not None]
            if len(owner._continuities) >= 128:
                raise ChallengeError("reviewed policy capacity")
            owner._continuities.append(weakref.ref(continuity))


class ReviewedIngressPolicy:
    def __init__(self, anchor_store=None):
        self._lock = threading.RLock()
        self._lease = None
        self._continuities = []
        self._anchor_store = anchor_store

    def current(self, authority):
        with self._lock:
            if self._lease is None or self._lease.authority != authority:
                raise ChallengeError("reviewed policy unavailable")
            return self._lease

    def install(self, evidence, binding=None):
        """Install only opaque evidence minted by its still-live proof client."""
        if not isinstance(evidence, _LiveClientEvidence):
            raise ChallengeError("live reviewed-policy evidence required")
        authority = evidence.claim()
        review = _review_sha256(authority)
        if self._anchor_store is None:
            if binding is not None:
                raise ChallengeError("unexpected policy anchor binding")
            generation = uuid.uuid4()
        else:
            from .reviewed_policy_anchor import Binding
            if (not isinstance(binding, Binding) or binding.authority != authority or
                    binding.review_sha256 != review):
                raise ChallengeError("policy anchor binding unavailable")
            generation = self._anchor_store.load_or_create(binding)
        with self._lock:
            if self._lease is not None:
                lease = self._lease
                if (lease.authority != authority or lease.generation != generation or
                        lease.review_sha256 != review):
                    raise ChallengeError("reviewed policy already installed")
                lease._fresh = True
                return lease
            lease = _Lease(self, authority, generation, review, True)
            self._lease = lease
            return lease

    def restore(self, binding):
        """Install a recovery-only lease from an exact caller-derived binding."""
        if self._anchor_store is None:
            raise ChallengeError("policy anchor unavailable")
        generation = self._anchor_store.load(binding)
        review = _review_sha256(binding.authority)
        if binding.review_sha256 != review:
            raise ChallengeError("policy review changed")
        with self._lock:
            if self._lease is not None:
                raise ChallengeError("reviewed policy already installed")
            lease = _Lease(self, binding.authority, generation, review, False)
            self._lease = lease
            return lease

    def invalidate(self):
        with self._lock:
            self._lease = None
            for value in self._continuities:
                continuity = value()
                if continuity is not None:
                    continuity.invalidate()
            self._continuities = []

    def __del__(self):
        # A retained lease/snapshot must not outlive its policy owner as trust.
        self.invalidate()
