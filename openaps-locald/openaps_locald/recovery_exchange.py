"""One-use recovery evidence owner; no admission, persistence or dispatch.

Construct only after reserving shared connection budgets and resolving admitted
keys. The caller must revalidate configuration/key/policy when committing.
"""
import math
import threading
from collections import namedtuple
from types import MappingProxyType

from .authorization_tls import boottime
from .device_identity import credential_id_for_public_key
from .write_challenge import ChallengeError
from . import recovery_challenge as codec

RecoveryEvidence = namedtuple("RecoveryEvidence", "request contact_age_upper_bound issued_at verified_at "
                              "signed_response witness_public_key_der")


class RecoveryExchange:
    def __init__(self, authority, requester, requester_kind, witness, witness_kind,
                 witness_key_der, connection_id, verifier_identity, clock=boottime):
        if (not isinstance(witness_key_der, bytes) or len(witness_key_der) != 91 or
                credential_id_for_public_key(witness_key_der) != witness):
            raise ChallengeError("recovery witness key")
        now = clock()
        if not math.isfinite(now) or now < 0:
            raise ChallengeError("recovery clock")
        self._request = codec.fresh_request(authority, requester, requester_kind,
            witness, witness_kind, connection_id)
        self._key = witness_key_der
        self._identity = verifier_identity
        self._clock = clock
        self._issued = self._last = now
        self._consumed = False
        self._evidence = None
        self._cancelled = threading.Event()
        self._lock = threading.Lock()

    def cancel(self):
        # Must not wait for a running OpenSSL verification.
        self._cancelled.set()

    def _check_time(self):
        now = self._clock()
        if (self._cancelled.is_set() or not math.isfinite(now) or
                now < self._last or now - self._issued >= 20):
            self._cancelled.set()
            raise ChallengeError("recovery unavailable")
        self._last = now
        return now

    def _enter(self):
        if not self._lock.acquire(False):
            raise ChallengeError("recovery busy")

    def request_data(self):
        self._enter()
        try:
            if self._consumed:
                raise ChallengeError("recovery consumed")
            self._check_time()
            return codec.encode_request(self._request)
        finally:
            self._lock.release()

    def consume(self, response_data):
        self._enter()
        try:
            if self._consumed:
                raise ChallengeError("recovery consumed")
            self._consumed = True  # Any attempt burns the nonce, including malformed data.
            self._check_time()
            age = codec.verify_response_data(self._request, response_data, self._key, self._identity)
            verified = self._check_time()
            upper_bound = age + (verified - self._issued)
            if upper_bound >= 86400:
                raise ChallengeError("recovery contact expired")
            self._evidence = RecoveryEvidence(MappingProxyType(dict(self._request)), upper_bound,
                self._issued, verified, bytes(response_data), bytes(self._key))
            return self._evidence
        finally:
            self._lock.release()

    def current_contact_age(self, evidence):
        """Recheck under the admission owner's commit guards; never a commit."""
        self._enter()
        try:
            if evidence is None or evidence is not self._evidence:
                raise ChallengeError("foreign recovery evidence")
            now = self._check_time()
            age = evidence.contact_age_upper_bound + (now - evidence.verified_at)
            if age >= 86400:
                raise ChallengeError("recovery contact expired")
            return age
        finally:
            self._lock.release()
