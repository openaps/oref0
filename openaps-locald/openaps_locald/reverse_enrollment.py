"""Phone-initiated reverse proof workflow. No HTTP data establishes trust.

The runtime supplies a bounded proof client and actual AdmissionOwner factory;
there is no policy installer or arbitrary context guard in this workflow.
"""
import base64
import math
import re
import threading

from .admission_owner import AdmissionOwner
from .authorization_tls import boottime
from .device_identity import credential_id_for_public_key, validate_public_key_der
from .write_challenge import validate_challenge, ChallengeError

BEGIN = "openaps.ns-reverse-begin.v1"
READY = "openaps.ns-reverse-ready.v1"
CHALLENGE = "openaps.ns-reverse-challenge.v1"


class ReverseEnrollmentWorkflow:
    def __init__(self, client, identity, authority, owner_for_peer, clock=boottime,
                 did_commit=None, did_discard=None):
        self.client, self.identity, self.authority = client, identity, authority
        self.owner_for_peer, self.clock = owner_for_peer, clock
        self.operation, self.lock = threading.Lock(), threading.RLock()
        self.valid, self.last, self.pending = True, None, None
        self.did_commit, self.did_discard = did_commit, did_discard

    def _time(self):
        with self.lock:
            now = self.clock()
            if not self.valid or not math.isfinite(now) or now < 0 or (self.last is not None and now < self.last):
                self.valid = False
                raise ChallengeError("reverse clock unavailable")
            self.last = now
            return now

    def _check(self, job):
        with self.lock:
            now = self._time()
            if self.pending is not job or now - job["started"] >= 120:
                raise ChallengeError("reverse job unavailable")
            job["owner"].validate_enrollment_context(self.client, self.authority,
                self.identity.credential_id, job["phone"])
            if self._time() - job["started"] >= 120:
                raise ChallengeError("reverse context check expired")

    def _discard(self, job, invalidate_owner=True):
        with self.lock:
            if self.pending is job:
                self.pending = None
            challenge = job.get("challenge")
            if challenge is not None:
                self.client.cancel_challenge(challenge["nonce"])
            if invalidate_owner:
                job["owner"].invalidate()
            if self.did_discard is not None:
                self.did_discard(job["owner"], job["key"])

    def invalidate(self):
        with self.lock:
            self.valid = False
            if self.pending is not None:
                self._discard(self.pending)

    def handle(self, body, started_at=None):
        if not self.operation.acquire(False):
            return 429, None
        try:
            try:
                started = self._time()
                if started_at is not None:
                    if not math.isfinite(started_at) or not 0 <= started_at <= started:
                        raise ChallengeError("reverse transport clock")
                    started = started_at
                with self.lock:
                    if self.pending is not None and self._time() - self.pending["started"] >= 120:
                        self._discard(self.pending, invalidate_owner=not self.pending.get("complete", False))
                if not isinstance(body, dict):
                    return 400, None
                if body.get("schema") == BEGIN:
                    return self._begin(body, started)
                if body.get("schema") == READY:
                    return self._complete(body)
                return 400, None
            except Exception:
                with self.lock:
                    if self.pending is not None:
                        self._discard(self.pending, invalidate_owner=not self.pending.get("complete", False))
                return 503, None
        finally:
            self.operation.release()

    def _begin(self, body, started):
        try:
            if set(body) != {"schema", "challenge", "phone_public_key_der"}:
                return 400, None
            original = validate_challenge(body["challenge"])
            encoded = body["phone_public_key_der"]
            if not isinstance(encoded, str) or len(encoded) != 124:
                return 400, None
            key = base64.b64decode(encoded, validate=True)
            if len(key) != 91 or base64.b64encode(key).decode("ascii") != encoded:
                return 400, None
            phone = credential_id_for_public_key(key)
            if (original["authority_context_id"] != self.authority or
                    original["peer_credential_id"] != self.identity.credential_id or
                    original["peer_device_kind"] != "rig" or original["verifier_device_kind"] != "phone" or
                    original["verifier_credential_id"] != phone):
                return 400, None
            validate_public_key_der(key, self.identity.openssl_path, self.identity.openssl_lock_path)
        except Exception:
            return 400, None
        with self.lock:
            if self.pending is not None:
                job = self.pending
                if job["original"] != original or job["key"] != key:
                    return 429, None
                self._check(job)
                return 200, {"schema": CHALLENGE, "challenge": dict(job["challenge"])}
            print("openaps authorization reverse stage=owner_begin", flush=True)
            owner = self.owner_for_peer(key)
            try:
                if not isinstance(owner, AdmissionOwner):
                    raise ChallengeError("reverse admission owner unavailable")
                owner.validate_enrollment_context(self.client, self.authority, self.identity.credential_id, phone,
                                                  require_unadmitted=True)
                job = {"started": started, "owner": owner, "original": original, "key": key,
                       "phone": phone, "challenge": None, "polls": 0, "complete": False}
                self.pending = job
                print("openaps authorization reverse stage=owner_ready", flush=True)
            except Exception:
                # The factory may already have reserved a fresh registry slot.
                # Only that factory's exact-attempt cleanup may invalidate it:
                # the rejected object might instead be an existing active owner.
                if self.did_discard is not None:
                    self.did_discard(owner, key)
                raise
        self._check(job)
        print("openaps authorization reverse stage=permissions_begin", flush=True)
        before = self.client.observe_enrollment_permissions()
        print("openaps authorization reverse stage=permissions_ready", flush=True)
        self._check(job)
        if before.outcome != "denied_known_writes":
            raise ChallengeError("reverse ingress observation unavailable")
        print("openaps authorization reverse stage=challenge_begin", flush=True)
        challenge = self.client.issue_challenge(phone, "phone")
        print("openaps authorization reverse stage=challenge_ready", flush=True)
        with self.lock:
            if self.pending is not job:
                self.client.cancel_challenge(challenge["nonce"])
                raise ChallengeError("reverse issuance invalidated")
            job["challenge"], job["before"] = challenge, before
        self._check(job)
        if (challenge["nonce"] == original["nonce"] or challenge["authority_context_id"] != self.authority or
                challenge["verifier_credential_id"] != self.identity.credential_id or
                challenge["verifier_device_kind"] != "rig" or challenge["peer_credential_id"] != phone or
                challenge["peer_device_kind"] != "phone"):
            raise ChallengeError("reverse issuer context")
        return 200, {"schema": CHALLENGE, "challenge": dict(challenge)}

    def _complete(self, body):
        if (set(body) != {"schema", "nonce"} or not isinstance(body["nonce"], str) or
                not re.fullmatch(r"[0-9a-f]{64}", body["nonce"])):
            return 400, None
        with self.lock:
            job = self.pending
            if job is None or job.get("challenge") is None or job["challenge"]["nonce"] != body["nonce"]:
                return 400, None
            self._check(job)
            if job["complete"]:
                return 202, None # One bounded tombstone, same original deadline.
            if job["polls"] >= 4:
                raise ChallengeError("reverse polling limit")
            job["polls"] += 1
        receipt = self.client.read_fresh_peer_response(body["nonce"], job["key"])
        self._check(job)
        if receipt is None:
            return 425, None
        after = self.client.observe_enrollment_permissions()
        self._check(job)
        job["owner"].admit_fresh(receipt, job["before"], after)
        self._check(job) # Late failure invalidates a possibly committed snapshot.
        with self.lock:
            self._check(job)
            if self.did_commit is not None:
                self.did_commit(job["owner"], job["key"], lambda: self._check(job))
            job["complete"] = True
        return 202, None
