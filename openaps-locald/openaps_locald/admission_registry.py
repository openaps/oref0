"""Injected live rig registry. No startup activation, shadow fallback or restore.

One fresh attempt owner is separate from at most 32 active peer owners. Public
failed enrollment can never replace/invalidate an existing active peer owner.
"""
import contextlib
import hashlib
import json
import math
import os
import tempfile
import threading
import uuid
from collections import namedtuple

from .admission_owner import AdmissionOwner, LiveAdmissionContext
from .admission_record import Context
from .authorization_tls import boottime
from . import committed_admission
from .authorization_protocol import registry_identifier
from .device_identity import credential_id_for_public_key, validate_public_key_der
from .reviewed_ingress_policy import _Lease
from .reverse_enrollment import ReverseEnrollmentWorkflow
from .write_challenge import ChallengeError

RegistryScope = namedtuple("RegistryScope", "authority local_credential_id settings_epoch "
    "local_key_generation policy_generation policy_review_sha256")

_ACTIVE_MARKER_SCHEMA = "openaps.committed-active-peer.v1"
_ACTIVE_MARKER_NAME = "active-peer.v1.json"
_ACTIVE_MARKER_MAX_BYTES = 4096
_ACTIVE_MARKER_TTL_SECONDS = 10 * 60


class _PeerLiveContext(LiveAdmissionContext):
    def __init__(self, parent, scope, context):
        super(_PeerLiveContext, self).__init__(context)
        self.parent, self.scope = parent, scope

    @contextlib.contextmanager
    def hold(self, expected):
        with self.parent.hold(self.scope):
            with super(_PeerLiveContext, self).hold(expected):
                yield


class AdmissionRegistry:
    def __init__(self, client, identity, candidate_storage, committed_storage,
                 scope, live_context, policy,
                 validate_persisted_scope, clock=boottime, maximum=32):
        if (not isinstance(scope, RegistryScope) or not isinstance(live_context, LiveAdmissionContext) or
                not isinstance(policy, _Lease) or isinstance(maximum, bool) or
                not isinstance(maximum, int) or not 1 <= maximum <= 32 or
                not all(isinstance(value, uuid.UUID) for value in
                        (scope.settings_epoch, scope.local_key_generation, scope.policy_generation)) or
                scope.local_credential_id != identity.credential_id or scope.authority != policy.authority or
                scope.policy_generation != policy.generation or scope.policy_review_sha256 != policy.review_sha256):
            raise ChallengeError("registry context unavailable")
        if committed_storage is candidate_storage:
            raise ChallengeError("dedicated committed storage required")
        self.client, self.identity, self.storage = client, identity, candidate_storage
        self.committed_storage = committed_storage
        self.scope, self.live, self.policy = scope, live_context, policy
        self.validate_persisted, self.clock, self.maximum = validate_persisted_scope, clock, maximum
        self.lock, self.valid = threading.RLock(), True
        self.active, self.recovering, self.pending = {}, {}, None
        self.last_recent_commit_failure = None
        with self._guard(persisted=True):
            pass
        self.reverse_workflow = ReverseEnrollmentWorkflow(client, identity, scope.authority,
            self._fresh_owner, clock=clock, did_commit=self._promote, did_discard=self._discard)

    @contextlib.contextmanager
    def _guard(self, persisted=False):
        # Context/policy precede registry and owner locks everywhere.
        with self.live.hold(self.scope):
            with self.policy.hold():
                with self.lock:
                    if not self.valid or self.identity.credential_id != self.scope.local_credential_id:
                        raise ChallengeError("registry invalidated")
                    if persisted:
                        self.validate_persisted(self.scope)
                    yield
                    if not self.valid:
                        raise ChallengeError("registry invalidated")

    def _fresh_owner(self, key):
        self.policy.require_fresh()
        validate_public_key_der(key, self.identity.openssl_path, self.identity.openssl_lock_path)
        peer = credential_id_for_public_key(key)
        with self._guard(persisted=True):
            if (peer == self.scope.local_credential_id or self.pending is not None or
                    peer in self.recovering or
                    (peer not in self.active and
                     len(self.active) + len(self.recovering) >= self.maximum)):
                raise ChallengeError("registry attempt capacity")
            context = Context(self.scope.authority, self.scope.local_credential_id, "rig", peer,
                self.scope.settings_epoch, self.scope.local_key_generation,
                self.scope.policy_generation, self.scope.policy_review_sha256)
            live = _PeerLiveContext(self.live, self.scope, context)
            def validate(expected):
                if expected != context:
                    raise ChallengeError("registry peer context changed")
                self.validate_persisted(self.scope)
            owner = AdmissionOwner(self.client, self.storage, context, self.identity, live, self.policy,
                validate, clock=self.clock, committed_storage=self.committed_storage)
            self.pending = (peer, key, owner)
            return owner

    def recovery_required(self, peer_credential_id, peer_public_key_der):
        """Explicit exact-peer restore selection; never activates an admission."""
        validate_public_key_der(peer_public_key_der, self.identity.openssl_path,
                                self.identity.openssl_lock_path)
        if credential_id_for_public_key(peer_public_key_der) != peer_credential_id:
            raise ChallengeError("recovery peer key changed")
        with self._guard(persisted=True):
            if (peer_credential_id == self.scope.local_credential_id or self.pending is not None or
                    peer_credential_id in self.active or peer_credential_id in self.recovering or
                    len(self.active) + len(self.recovering) >= self.maximum):
                raise ChallengeError("registry recovery capacity")
            context = Context(self.scope.authority, self.scope.local_credential_id, "rig",
                peer_credential_id, self.scope.settings_epoch, self.scope.local_key_generation,
                self.scope.policy_generation, self.scope.policy_review_sha256)
            live = _PeerLiveContext(self.live, self.scope, context)
            def validate(expected):
                if expected != context:
                    raise ChallengeError("registry peer context changed")
                self.validate_persisted(self.scope)
            owner = AdmissionOwner(self.client, self.storage, context, self.identity, live, self.policy,
                validate, clock=self.clock, committed_storage=self.committed_storage)
            try:
                handle = owner.restore_recovery_required()
            except Exception:
                owner.invalidate()
                raise
            self.recovering[peer_credential_id] = (peer_public_key_der, owner)
            return owner, handle

    def cancel_recovery_owner(self, peer_credential_id, owner):
        removed = None
        with self.lock:
            entry = self.recovering.get(peer_credential_id)
            if entry is not None and entry[1] is owner:
                removed = self.recovering.pop(peer_credential_id)[1]
        if removed is not None:
            removed.invalidate()

    def commit_recovery_owner(self, peer_credential_id, owner, attempt, engine, completion):
        """Promote only an exact engine completion; never upgrade its connection."""
        try:
            revision = owner.commit_recovery(attempt, engine, completion)
            connection = str(uuid.uuid4())
            with self._guard(persisted=True):
                entry = self.recovering.get(peer_credential_id)
                if entry is None or entry[1] is not owner:
                    raise ChallengeError("registry recovery owner changed")
                key = entry[0]
                snapshot = owner.snapshot(connection)
                if snapshot["peer"]["public_key_der"] != key:
                    raise ChallengeError("registry recovered key changed")
                self._write_active_marker(peer_credential_id, key)
                self.active[peer_credential_id] = (key, owner)
                del self.recovering[peer_credential_id]
            return revision
        except Exception:
            self.cancel_recovery_owner(peer_credential_id, owner)
            raise

    def _promote(self, owner, key, validate_attempt):
        peer = credential_id_for_public_key(key)
        with self._guard(persisted=True):
            if self.pending != (peer, key, owner):
                raise ChallengeError("registry pending owner changed")
            owner.validate_enrollment_context(self.client, self.scope.authority, self.scope.local_credential_id, peer)
            snapshot = owner.snapshot(str(uuid.uuid4()))
            if snapshot["peer"]["public_key_der"] != key:
                raise ChallengeError("registry committed key changed")
            validate_attempt() # Original deadline and current context, before the swap.
            self._write_active_marker(peer, key)
            previous = self.active.get(peer)
            self.active[peer] = (key, owner)
            self.pending = None
            if previous is not None:
                previous[1].invalidate()

    def _discard(self, owner, key):
        with self.lock:
            if self.pending is not None and self.pending[1:] == (key, owner):
                self.pending = None
                owner.invalidate() # Only this registry's fresh attempt, never active.

    def snapshot(self, peer_credential_id, connection):
        with self._guard():
            entry = self.active.get(peer_credential_id)
            if entry is None:
                raise ChallengeError("registry peer not admitted")
            key, owner = entry
            result = owner.snapshot(connection)
            if result["peer"]["public_key_der"] != key:
                raise ChallengeError("registry peer key changed")
            return result

    def recovery_witness(self, peer_credential_id, peer_public_key_der):
        """Select one exact active peer for a restricted witness exchange.

        The returned provider keeps the registry/owner guards on every use;
        the continuity object is only the independently admitted witness and
        never a recovery or normal-session capability.
        """
        validate_public_key_der(peer_public_key_der, self.identity.openssl_path,
                                self.identity.openssl_lock_path)
        if credential_id_for_public_key(peer_public_key_der) != peer_credential_id:
            raise ChallengeError("recovery witness key changed")
        with self._guard(persisted=True):
            entry = self.active.get(peer_credential_id)
            if entry is None or entry[0] != peer_public_key_der:
                raise ChallengeError("recovery witness unavailable")
            owner = entry[1]
            connection = str(uuid.uuid4())
            snapshot = owner.snapshot(connection)
            if snapshot["peer"]["public_key_der"] != peer_public_key_der:
                raise ChallengeError("recovery witness key changed")
            return (lambda: owner.snapshot(connection)), snapshot["continuity"]

    def provider(self, peer_credential_id, connection):
        # Capture this registry and exact peer/connection, never a shadow record.
        self.snapshot(peer_credential_id, connection)
        return lambda: self.snapshot(peer_credential_id, connection)

    def active_peer(self, peer_credential_id):
        """Return the exact key for an already-active admitted peer.

        This is a read-only bridge for the BLE shadow verifier after a
        recovery exchange has committed a peer locally. It never creates an
        owner, performs Nightscout I/O, or promotes a candidate; the returned
        key is sourced from the same active owner snapshot used by TLS.
        """
        with self._guard():
            entry = self.active.get(peer_credential_id)
            if entry is None:
                return None
            key, owner = entry
            snapshot = owner.snapshot(str(uuid.uuid4()))
            peer = snapshot.get("peer")
            if not isinstance(peer, dict) or peer.get("credential_id") != peer_credential_id:
                raise ChallengeError("registry active peer changed")
            if peer.get("public_key_der") != key:
                raise ChallengeError("registry active peer key changed")
            return dict(peer)

    def record_authenticated_contact(self, peer_credential_id):
        """Refresh the sibling-process marker after proven mutual TLS use.

        The caller must invoke this only after the TLS session has authenticated
        the peer and accepted an application request for this rig. Merely naming
        a credential, opening a socket, or presenting an invalid request cannot
        extend the cross-process marker.
        """
        with self._guard(persisted=True):
            entry = self.active.get(peer_credential_id)
            if entry is None:
                raise ChallengeError("registry active peer unavailable")
            key, owner = entry
            snapshot = owner.snapshot(str(uuid.uuid4()))
            peer = snapshot.get("peer")
            if (not isinstance(peer, dict) or
                    peer.get("credential_id") != peer_credential_id or
                    peer.get("public_key_der") != key):
                raise ChallengeError("registry authenticated peer changed")
            self._write_active_marker(peer_credential_id, key)

    def recently_committed_peer(self, peer_credential_id):
        """Return a just-committed peer for a sibling daemon process.

        The HTTP and BLE daemons intentionally own separate registries. A
        short-lived marker lets the BLE process consume the exact committed
        admission after recovery without copying live owners or trusting the
        legacy Nightscout collection. The marker is only a routing hint: the
        durable signed archive remains authoritative and its key must match the
        marker digest exactly.
        """
        try:
            self.last_recent_commit_failure = None
            marker, archive_data = self._read_active_marker_and_archive()
            if marker is None:
                self.last_recent_commit_failure = "marker_missing_or_unsafe"
                return None
            names = {"schema", "authority", "local_credential_id", "local_kind",
                     "peer_credential_id", "registry_identifier", "public_key_sha256",
                     "committed_at"}
            if (set(marker) != names or any(not isinstance(value, str) for value in marker.values()) or
                    marker["schema"] != _ACTIVE_MARKER_SCHEMA or
                    marker["authority"] != self.scope.authority or
                    marker["local_credential_id"] != self.scope.local_credential_id or
                    marker["local_kind"] != "rig" or
                    marker["peer_credential_id"] != peer_credential_id or
                    marker["registry_identifier"] != registry_identifier(peer_credential_id) or
                    not isinstance(marker["public_key_sha256"], str) or
                    len(marker["public_key_sha256"]) != 64):
                self.last_recent_commit_failure = "marker_shape_or_scope"
                return None
            committed_at = float(marker["committed_at"])
            now = float(self.clock())
            if (not math.isfinite(committed_at) or str(committed_at) != marker["committed_at"] or
                    not math.isfinite(now) or committed_at > now or
                    now - committed_at >= _ACTIVE_MARKER_TTL_SECONDS):
                self.last_recent_commit_failure = "marker_time"
                return None
            context = Context(self.scope.authority, self.scope.local_credential_id, "rig",
                peer_credential_id, self.scope.settings_epoch, self.scope.local_key_generation,
                self.scope.policy_generation, self.scope.policy_review_sha256)
            audit = committed_admission.CommittedArchive(archive_data).record(context, self.identity)
            if audit is None:
                self.last_recent_commit_failure = "archive_scope_or_signature"
                return None
            key = audit.candidate.proof.public_key_der
            validate_public_key_der(key, self.identity.openssl_path, self.identity.openssl_lock_path)
            if (credential_id_for_public_key(key) != peer_credential_id or
                    hashlib.sha256(key).hexdigest() != marker["public_key_sha256"]):
                self.last_recent_commit_failure = "peer_key_mismatch"
                return None
            return {"credential_id": peer_credential_id, "public_key_der": key,
                    "device_kind": "phone", "authority_context_id": self.scope.authority,
                    "realm_id": self.scope.authority,
                    "registry_identifier": registry_identifier(peer_credential_id)}
        except Exception as exc:
            self.last_recent_commit_failure = "exception_" + type(exc).__name__
            # Cross-process shadow lookup is fail-closed and must never affect
            # the legacy service if a marker/archive is stale or malformed.
            return None

    def _active_marker_path(self):
        return os.path.join(self.committed_storage._directory, _ACTIVE_MARKER_NAME)

    def _write_active_marker(self, peer_credential_id, key):
        if (not isinstance(peer_credential_id, str) or
                credential_id_for_public_key(key) != peer_credential_id):
            raise ChallengeError("active marker peer key")
        marker = {"schema": _ACTIVE_MARKER_SCHEMA, "authority": self.scope.authority,
            "local_credential_id": self.scope.local_credential_id, "local_kind": "rig",
            "peer_credential_id": peer_credential_id,
            "registry_identifier": registry_identifier(peer_credential_id),
            "public_key_sha256": hashlib.sha256(key).hexdigest(),
            "committed_at": str(float(self.clock()))}
        encoded = json.dumps(marker, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")
        if len(encoded) > _ACTIVE_MARKER_MAX_BYTES:
            raise ChallengeError("active marker size")
        temporary = ".active-peer-" + uuid.uuid4().hex
        fd = None
        created = False
        with self.committed_storage._transaction() as root:
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW, 0o600, dir_fd=root)
                created = True
                remaining = memoryview(encoded)
                while remaining:
                    count = os.write(fd, remaining)
                    if count <= 0:
                        raise ChallengeError("active marker write stalled")
                    remaining = remaining[count:]
                os.fsync(fd)
                os.close(fd)
                fd = None
                os.replace(temporary, _ACTIVE_MARKER_NAME, src_dir_fd=root, dst_dir_fd=root)
                created = False
                os.fsync(root)
            finally:
                if fd is not None:
                    os.close(fd)
                if created:
                    try:
                        os.unlink(temporary, dir_fd=root)
                    except FileNotFoundError:
                        pass

    def _read_active_marker_and_archive(self):
        with self.committed_storage._transaction() as root:
            try:
                fd = os.open(_ACTIVE_MARKER_NAME, os.O_RDONLY | os.O_NOFOLLOW |
                             os.O_NONBLOCK, dir_fd=root)
            except FileNotFoundError:
                return None, self.committed_storage._load(root)
            try:
                info = os.fstat(fd)
                if (info.st_uid != os.geteuid() or info.st_mode & 0o077 or
                        info.st_nlink != 1 or not 0 < info.st_size <= _ACTIVE_MARKER_MAX_BYTES):
                    return None, self.committed_storage._load(root)
                data = os.read(fd, _ACTIVE_MARKER_MAX_BYTES + 1)
                if len(data) != info.st_size:
                    return None, self.committed_storage._load(root)
            finally:
                os.close(fd)
            try:
                marker = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeError):
                marker = None
            return marker, self.committed_storage._load(root)

    def invalidate(self):
        # Do not hold registry lock while acquiring workflow's operation lock.
        with self.lock:
            self.valid = False
            owners = [entry[1] for entry in self.active.values()]
            owners.extend(entry[1] for entry in self.recovering.values())
            if self.pending is not None:
                owners.append(self.pending[2])
            self.active, self.recovering, self.pending = {}, {}, None
        self.reverse_workflow.invalidate()
        for owner in owners:
            owner.invalidate()
