"""Cross-process secure-mode readiness and route-owner consumption.

The HTTP and BLE owners run as separate processes.  This module gives them a
small, durable readiness bus backed by the private secure-mode directory:
each owner signs its current scope, process instance and heartbeat; either
owner may publish the prepared generation once both reports agree; each owner
arms that exact generation locally; and the committed contract is accepted
only while both fresh armed reports are still present.  A missing, stale,
malformed or mismatched report is unavailable, never permission.

The whole mechanism is dormant unless ``authorization_secure_mode_enabled`` is
explicitly true.  It is intentionally independent of clinical data and uses
the same local identity and exact admission scope as the TLS owner.
"""
from __future__ import print_function

import base64
import json
import os
import re
import stat
import threading
import time
import uuid
from collections import namedtuple

from .admission_storage import AdmissionStorage
from .secure_mode import SecureModePolicy
from .secure_mode_contract import (Binding, SecureModeContractStore,
                                   decode_record, decode_signed_record)
from .secure_mode_supervisor import Scope
from .stored_proof import _object
from .write_challenge import ChallengeError


STATUS_SCHEMA = "openaps.secure-mode-owner.v1"
STATUS_DOMAIN = b"openaps-secure-mode-owner-signature-v1\0"
STATUS_MAX_BYTES = 4096
HEARTBEAT_TTL_MS = 5000
HEARTBEAT_INTERVAL_MS = 1000
MAX_FUTURE_HEARTBEAT_MS = 1000
Status = namedtuple("Status", "role instance scope phase heartbeat_ms")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _ensure_private_directory(path):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ChallengeError("secure-mode directory")
    try:
        os.mkdir(path, 0o700)
    except OSError:
        if not os.path.isdir(path):
            raise ChallengeError("secure-mode directory")
    info = os.lstat(path)
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or
            info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ChallengeError("secure-mode directory privacy")


def _scope_fields(scope):
    if not isinstance(scope, Scope):
        raise ChallengeError("secure-mode scope")
    return {
        "authority": scope.authority,
        "local_credential_id": scope.local_credential_id,
        "settings_epoch": str(scope.settings_epoch),
        "key_epoch": str(scope.key_epoch),
        "policy_generation": str(scope.policy_generation),
        "policy_review_sha256": scope.policy_review_sha256,
    }


def _scope_from(fields):
    try:
        return Scope(
            fields["authority"], fields["local_credential_id"],
            uuid.UUID(fields["settings_epoch"]), uuid.UUID(fields["key_epoch"]),
            uuid.UUID(fields["policy_generation"]), fields["policy_review_sha256"],
        )
    except (KeyError, TypeError, ValueError):
        raise ChallengeError("secure-mode scope encoding") from None


def _unsigned_status(role, instance, scope, phase, heartbeat_ms, credential_id):
    if role not in ("http", "ble"):
        raise ChallengeError("secure-mode owner role")
    if not isinstance(instance, uuid.UUID) or instance.int == 0:
        raise ChallengeError("secure-mode owner instance")
    if phase not in ("ready", "armed", "aborted"):
        raise ChallengeError("secure-mode owner phase")
    if not isinstance(heartbeat_ms, int) or heartbeat_ms <= 0:
        raise ChallengeError("secure-mode owner heartbeat")
    fields = {"schema": STATUS_SCHEMA, "role": role, "instance": str(instance),
              "local_credential_id": credential_id, "phase": phase,
              "heartbeat_ms": str(heartbeat_ms)}
    fields.update(_scope_fields(scope))
    return fields


def encode_status(role, instance, scope, phase, heartbeat_ms, identity):
    fields = _unsigned_status(role, instance, scope, phase, heartbeat_ms,
                              identity.credential_id)
    fields["signature"] = base64.b64encode(
        identity.sign(STATUS_DOMAIN + _json(fields))).decode("ascii")
    data = _json(fields)
    if len(data) > STATUS_MAX_BYTES:
        raise ChallengeError("secure-mode owner status size")
    return data


def decode_status(data, identity, expected_role=None):
    obj = _object(data, maximum_bytes=STATUS_MAX_BYTES, maximum_depth=1)
    names = {"schema", "role", "instance", "local_credential_id", "phase",
             "heartbeat_ms", "authority", "settings_epoch", "key_epoch",
             "policy_generation", "policy_review_sha256", "signature"}
    if (not isinstance(obj, dict) or set(obj) != names or
            any(not isinstance(value, str) for value in obj.values()) or
            obj.get("schema") != STATUS_SCHEMA or _json(obj) != data):
        raise ChallengeError("secure-mode owner status shape")
    fields = dict(obj)
    encoded_signature = fields.pop("signature")
    try:
        role = fields["role"]
        instance = uuid.UUID(fields["instance"])
        phase = fields["phase"]
        heartbeat_ms = int(fields["heartbeat_ms"])
        scope = _scope_from(fields)
        signature = base64.b64decode(encoded_signature, validate=True)
    except (KeyError, TypeError, ValueError):
        raise ChallengeError("secure-mode owner status encoding") from None
    if (expected_role is not None and role != expected_role or
            fields["local_credential_id"] != identity.credential_id or
            base64.b64encode(signature).decode("ascii") != encoded_signature or
            not identity.verify(STATUS_DOMAIN + _json(fields), signature,
                                identity.credential_id, identity.public_key_der)):
        raise ChallengeError("secure-mode owner status signature or scope")
    _unsigned_status(role, instance, scope, phase, heartbeat_ms,
                     identity.credential_id)
    return Status(role, instance, scope, phase, heartbeat_ms)


class SecureModeRouteOwner(object):
    """One HTTP or BLE process's durable secure-mode owner."""

    def __init__(self, config, authorization_runtime, role,
                 heartbeat_ttl_ms=HEARTBEAT_TTL_MS,
                 heartbeat_interval_ms=HEARTBEAT_INTERVAL_MS, clock=None):
        if role not in ("http", "ble"):
            raise ChallengeError("secure-mode owner role")
        self.config = config
        self.runtime = authorization_runtime
        self.role = role
        self.instance = uuid.uuid4()
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.heartbeat_ttl_ms = max(1000, int(heartbeat_ttl_ms))
        self.heartbeat_interval_ms = max(250, int(heartbeat_interval_ms))
        self._stop = threading.Event()
        self._thread = None
        self._storage_error = None
        self._root = config.get("authorization_secure_mode_dir")
        self._stores = {}
        self._heartbeat_stores = {}
        self._status_cache = {}
        self._contract_cache = None
        self._contract_storage = None
        try:
            _ensure_private_directory(self._root)
            _ensure_private_directory(os.path.join(self._root, "contract"))
            for owner_role in ("http", "ble"):
                _ensure_private_directory(os.path.join(self._root, owner_role))
                _ensure_private_directory(os.path.join(self._root, owner_role + "-heartbeat"))
                self._stores[owner_role] = AdmissionStorage(
                    os.path.join(self._root, owner_role))
                self._heartbeat_stores[owner_role] = AdmissionStorage(
                    os.path.join(self._root, owner_role + "-heartbeat"))
            self._contract_storage = AdmissionStorage(
                os.path.join(self._root, "contract"))
        except Exception as exc:
            self._storage_error = exc

    def _identity(self):
        return getattr(self.runtime, "identity", None)

    def _current_scope(self):
        try:
            capabilities = self.runtime.secure_mode_capabilities()
            registry = capabilities.get("registry") if isinstance(capabilities, dict) else None
            if (not isinstance(capabilities, dict) or capabilities.get("state") != "active" or
                    capabilities.get("error_category") is not None or registry is None):
                return None
            scope = registry.scope
            local_key_generation = getattr(scope, "local_key_generation", None)
            if local_key_generation is None:
                local_key_generation = scope.key_epoch
            return Scope(scope.authority, scope.local_credential_id,
                         scope.settings_epoch, local_key_generation,
                         scope.policy_generation, scope.policy_review_sha256)
        except Exception:
            return None

    def _contract_store(self, identity):
        if self._contract_storage is None:
            raise ChallengeError("secure-mode storage unavailable")
        return SecureModeContractStore(self._contract_storage, identity)

    def _read_status(self, role, identity):
        if role not in self._stores:
            return None
        try:
            data = self._stores[role].load()
            if data is None:
                return None
            cached = self._status_cache.get(role)
            status = cached[1] if cached is not None and cached[0] == data else None
            if status is None:
                status = decode_status(data, identity, expected_role=role)
                self._status_cache[role] = (data, status)
            heartbeat = None
            heartbeat_data = self._heartbeat_stores[role].load()
            if heartbeat_data is not None:
                heartbeat = int(heartbeat_data.decode("ascii"))
            return status._replace(heartbeat_ms=heartbeat or status.heartbeat_ms)
        except Exception:
            return None

    def _write_status(self, phase, scope, identity, heartbeat_ms=None):
        if self.role not in self._stores:
            raise ChallengeError("secure-mode owner storage unavailable")
        heartbeat_ms = heartbeat_ms or int(self.clock())
        existing_data = self._stores[self.role].load()
        if existing_data is not None:
            # Never repair an unverified owner record implicitly.  A manual
            # cleanup/re-enrollment decision is required for malformed bytes.
            decode_status(existing_data, identity, expected_role=self.role)
        own = self._read_status(self.role, identity)
        if (own is None or own.instance != self.instance or own.scope != scope or
                own.phase != phase):
            data = encode_status(self.role, self.instance, scope, phase,
                                  heartbeat_ms, identity)
            self._stores[self.role].replace(data)
            self._status_cache[self.role] = (
                data, Status(self.role, self.instance, scope, phase, heartbeat_ms))
        self._heartbeat_stores[self.role].replace(
            str(int(heartbeat_ms)).encode("ascii"))

    def _fresh(self, status, now):
        age = now - status.heartbeat_ms
        return 0 <= age <= self.heartbeat_ttl_ms and age >= -MAX_FUTURE_HEARTBEAT_MS

    def _binding(self, scope, http, ble):
        if (http is None or ble is None or http.scope != scope or ble.scope != scope or
                http.instance == ble.instance):
            raise ChallengeError("secure-mode owner scope mismatch")
        return Binding(*(tuple(scope) + (http.instance, ble.instance)))

    def _contract_state(self, binding, identity):
        try:
            data = self._contract_storage.load()
            if data is None:
                self._contract_cache = None
                return None
            cached = self._contract_cache
            if cached is not None and cached[0] == data and cached[1] == binding:
                return cached[2]
            try:
                state = decode_record(data, binding, identity)
            except Exception:
                state = None
            self._contract_cache = (data, binding, state)
            return state
        except Exception:
            return None

    def _reports(self, scope, identity, phases):
        now = int(self.clock())
        http = self._read_status("http", identity)
        ble = self._read_status("ble", identity)
        if (http is None or ble is None or http.scope != scope or ble.scope != scope or
                http.phase not in phases or ble.phase not in phases or
                not self._fresh(http, now) or not self._fresh(ble, now)):
            return None
        return http, ble

    def _prepare(self, scope, identity):
        reports = self._reports(scope, identity, ("ready", "armed"))
        if reports is None:
            return None
        http, ble = reports
        try:
            binding = self._binding(scope, http, ble)
        except Exception:
            return None
        try:
            raw_contract = self._contract_storage.load()
        except Exception:
            return None
        state = self._contract_state(binding, identity)
        # A present contract that cannot be verified against this exact scope
        # must first be proven to be a valid older signed generation before a
        # two-owner restart may replace it; malformed bytes remain sticky.
        if raw_contract is not None and state is None:
            try:
                observed_binding, _old_generation, old_phase = decode_signed_record(
                    raw_contract, identity)
            except Exception:
                return None
            # A clean restart may replace an older signed generation, but only
            # after both fresh owners have published the new exact scope and
            # instances.  Malformed bytes never enter this branch.
            if old_phase not in ("prepared", "committed", "aborted"):
                return None
            if observed_binding != binding:
                generation = uuid.uuid4()
                try:
                    self._contract_store(identity).prepare(binding, generation)
                    return binding, generation, "prepared"
                except Exception:
                    return None
            return None
        if state is not None:
            generation, phase = state
            if phase in ("prepared", "committed"):
                return binding, generation, phase
        generation = uuid.uuid4()
        try:
            self._contract_store(identity).prepare(binding, generation)
            return binding, generation, "prepared"
        except Exception:
            return None

    def _arm(self, scope, identity, prepared):
        if prepared is None:
            return None
        binding, generation, phase = prepared
        if phase not in ("prepared", "committed"):
            return prepared
        state = self._contract_state(binding, identity)
        if state != (generation, phase):
            return prepared
        try:
            own = self._read_status(self.role, identity)
            if (own is None or own.instance != self.instance or own.scope != scope or
                    own.phase != "armed"):
                self._write_status("armed", scope, identity)
        except Exception:
            return prepared
        return prepared

    def _commit(self, scope, identity, prepared):
        if prepared is None:
            return False
        binding, generation, phase = prepared
        reports = self._reports(scope, identity, ("armed",))
        if reports is None:
            return False
        try:
            http, ble = reports
            if self._binding(scope, http, ble) != binding:
                return False
            if self._contract_state(binding, identity) != (generation, "prepared"):
                return self._contract_state(binding, identity) == (generation, "committed")
            self._contract_store(identity).commit(binding, generation)
            return True
        except Exception:
            return False

    def tick(self):
        """Advance one bounded readiness/heartbeat step."""
        if self.config.get("authorization_secure_mode_enabled") is not True:
            return False
        if self._storage_error is not None:
            return False
        identity = self._identity()
        scope = self._current_scope()
        if identity is None or scope is None:
            return False
        try:
            now = int(self.clock())
            own = self._read_status(self.role, identity)
            if (own is None or own.instance != self.instance or own.scope != scope or
                    own.phase == "aborted"):
                self._write_status("ready", scope, identity, now)
            elif now - own.heartbeat_ms >= self.heartbeat_interval_ms:
                # Keep the process heartbeat alive without changing its armed
                # state between coordination steps.
                self._heartbeat_stores[self.role].replace(str(now).encode("ascii"))
            prepared = self._prepare(scope, identity)
            self._arm(scope, identity, prepared)
            # Re-read after arming so this process cannot commit an old status.
            prepared = self._prepare(scope, identity)
            self._commit(scope, identity, prepared)
            return True
        except Exception:
            return False

    def policy(self):
        """Return a snapshot suitable for the HTTP or BLE route gate."""
        if self.config.get("authorization_secure_mode_enabled") is not True:
            return SecureModePolicy(SecureModePolicy.DISABLED)
        try:
            base = SecureModePolicy.evaluate(self.config, self.runtime)
        except Exception:
            return SecureModePolicy(SecureModePolicy.UNAVAILABLE, "runtime_error")
        if base.state != SecureModePolicy.READY:
            return base
        identity = self._identity()
        scope = self._current_scope()
        if identity is None or scope is None or self._storage_error is not None:
            return SecureModePolicy(SecureModePolicy.UNAVAILABLE, "owner_unavailable")
        reports = self._reports(scope, identity, ("armed",))
        if reports is None:
            return SecureModePolicy(SecureModePolicy.UNAVAILABLE, "owner_not_armed")
        try:
            binding = self._binding(scope, reports[0], reports[1])
        except Exception:
            return SecureModePolicy(SecureModePolicy.UNAVAILABLE, "owner_scope_mismatch")
        state = self._contract_state(binding, identity)
        if state is None or state[1] != "committed":
            return SecureModePolicy(SecureModePolicy.UNAVAILABLE, "contract_unavailable")
        return SecureModePolicy(SecureModePolicy.READY)

    def start(self, interval_seconds=1.0):
        if (self.config.get("authorization_secure_mode_enabled") is not True or
                self._thread is not None):
            return None
        self.tick()
        self._stop.clear()

        def run():
            while not self._stop.wait(interval_seconds):
                self.tick()

        self._thread = threading.Thread(
            target=run, name="openaps-secure-mode-%s" % self.role)
        self._thread.daemon = True
        self._thread.start()
        return self._thread

    def close(self):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(2)
        self._thread = None
        if self.config.get("authorization_secure_mode_enabled") is not True:
            return True
        identity = self._identity()
        scope = self._current_scope()
        if identity is None or scope is None or self._storage_error is not None:
            return False
        try:
            own = self._read_status(self.role, identity)
            if own is not None and own.instance == self.instance and own.scope == scope:
                self._write_status("aborted", scope, identity)
            reports = self._reports(scope, identity, ("ready", "armed"))
            if reports is not None:
                binding = self._binding(scope, reports[0], reports[1])
                state = self._contract_state(binding, identity)
                if state is not None and state[1] == "prepared":
                    self._contract_store(identity).abort(binding, state[0])
            return True
        except Exception:
            return False
