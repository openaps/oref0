from __future__ import print_function

import base64
import os
import sys
from collections import OrderedDict
import threading
import time
from types import MappingProxyType
from copy import deepcopy

from .device_identity import DeviceIdentity, IdentityError
from .authorization_replay import AuthorizationReplayStore
from .nightscout_write_proof import NightscoutWriteProofClient
from .nightscout_authorization import (
    _positive_integral_timestamp,
    NightscoutAuthorizationError,
    NightscoutDeviceAuthorizationClient,
)


SUCCESSFUL_PEER_REFRESH_SECONDS = 6 * 60 * 60
FAILED_PEER_REFRESH_THROTTLE_SECONDS = 5 * 60
SUCCESSFUL_SELF_RECONCILE_SECONDS = 6 * 60 * 60
FAILED_SELF_RECONCILE_THROTTLE_SECONDS = 5 * 60
FAILED_INITIALIZATION_RETRY_SECONDS = 5 * 60
MAX_PEER_REFRESH_HISTORY_ENTRIES = 128


class AuthorizationRuntime(object):
    """Process-local shadow coordinator; it never changes legacy allow/deny behavior."""

    def __init__(self, config, device_kind="rig", initialize_in_background=False,
                 enable_admission=False):
        # Configuration is startup-scoped, not a hot-reload interface. Own a
        # private snapshot so caller mutation cannot switch an initialized
        # authority/credential pair or race background initialization.
        self.config = MappingProxyType(deepcopy(config))
        self.device_kind = device_kind
        self.mode = self.config.get("authorization_mode") or "legacy"
        self.identity = None
        self.client = None
        self._proof_client = None
        self._admission_runtime = None
        self._enable_admission = enable_admission is True
        self._admission_activation_lock = threading.Lock()
        self._admission_activation_state = "not_started"
        self._admission_activation_error_category = None
        self._admission_retryable = False
        self._proof_lock = threading.Lock()
        self._proof_closed = threading.Event()
        self.replay = None
        self.carrier_ready_cached = False
        self.last_state = {"mode": self.mode, "classification": "not_started"}
        self._lookup_lock = threading.Lock()
        self._lookup_inflight = {}
        self._lookup_last_started = OrderedDict()
        self._lookup_refresh_intervals = {}
        self._monotonic = time.monotonic
        self._reconcile_async_lock = threading.Lock()
        self._reconcile_async_inflight = False
        self._reconcile_last_started = None
        self._reconcile_refresh_interval = 0
        self._periodic_reconcile_started = False
        self._initialization_lock = threading.Lock()
        self._initialization_inflight = False
        if self.mode != "shadow":
            return
        if initialize_in_background:
            self.last_state = {"mode": self.mode, "classification": "initializing"}
            self.initialize_async()
            return
        self._initialize()

    def _initialize(self):
        identity_directory = self.config.get("authorization_identity_dir")
        if not identity_directory:
            self.last_state = {"mode": self.mode, "classification": "missing_identity_directory"}
            return
        try:
            if self.identity is None:
                self.identity = DeviceIdentity(
                    identity_directory,
                    openssl_path=self.config.get("authorization_openssl_path"),
                )
        except IdentityError:
            self.last_state = {"mode": self.mode, "classification": "identity_error"}
            return
        except Exception:
            # Shadow initialization must never take down the legacy service.
            self.identity = None
            self.last_state = {
                "mode": self.mode,
                "classification": "initialization_error",
                "error_category": "identity_unexpected",
            }
            return
        base_url = self.config.get("nightscout_host")
        access_token = self.config.get("nightscout_access_token")
        api_secret = self.config.get("nightscout_api_secret")
        state_path = self.config.get("authorization_state_path")
        if not base_url or (not access_token and not api_secret) or not state_path:
            classification = "legacy_missing_nightscout_credential"
            if self.config.get("nightscout_credential_kind") == "legacy_api_secret":
                classification = "legacy_api_secret_unsupported"
            self.last_state = {
                "mode": self.mode,
                "classification": classification,
                "credential_id": self.identity.credential_id,
            }
            return
        try:
            client = NightscoutDeviceAuthorizationClient(
                base_url,
                access_token,
                self.identity,
                self.device_kind,
                state_path,
                api_secret=api_secret,
            )
            cached_self = client.trust.self_state()
            replay = AuthorizationReplayStore(state_path + ".replay.sqlite3")
        except Exception:
            self.client = None
            self.replay = None
            self.carrier_ready_cached = False
            self.last_state = {
                "mode": self.mode,
                "classification": "initialization_error",
                "error_category": "registry_state_unavailable",
                "credential_id": self.credential_id,
            }
            return
        self.client = client
        self.replay = replay
        self._prepare_proof_client()
        if cached_self:
            self.last_state = cached_self
            self.carrier_ready_cached = self._state_is_carrier_ready(cached_self)
        else:
            self.last_state = {
                "mode": self.mode,
                "classification": "initialized",
                "credential_id": self.credential_id,
            }

    def _prepare_proof_client(self):
        # Preparation only: no requests, workers, admission or shadow promotion.
        # Keep this owner private until bounded runtime job/teardown ownership
        # and reviewed-policy admission are integrated.
        if not self._proof_lock.acquire(False):
            return
        try:
            if self._proof_closed.is_set() or self._proof_client is not None or self.identity is None:
                return
            try:
                self._proof_client = NightscoutWriteProofClient(
                    self.config.get("nightscout_host"), self.identity, self.device_kind,
                    access_token=self.config.get("nightscout_access_token"),
                    api_secret=self.config.get("nightscout_api_secret"),
                    allow_insecure_http=self.config.get("allow_legacy_http_proof") is True)
            except Exception:
                # Preserve existing shadow/legacy classification on failure.
                self._proof_client = None
        finally:
            self._proof_lock.release()

    def close_proof_owner(self):
        """Nonblocking cancellation poll; retain this runtime until True.

        Does not stop legacy reconciliation. No proof jobs are enabled yet.
        A false result is live/uncertain cleanup, never permission to replace
        the owner and reset worker capacity.
        """
        self._proof_closed.set()
        with self._admission_activation_lock:
            if self._admission_activation_state != "active":
                self._admission_activation_state = "cancelled"
        if not self._proof_lock.acquire(False):
            return False
        try:
            if self._admission_runtime is not None:
                self._admission_runtime.invalidate()
                self._admission_runtime = None
            if self._proof_client is None:
                return True
            self._proof_client.invalidate()
            if not self._proof_client.reap_cancelled_network_worker():
                return False
            self._proof_client = None
            return True
        finally:
            self._proof_lock.release()

    def install_admission_registry(self, evidence):
        """Install one complete registry from caller-obtained live evidence.

        Construction performs durable local checks only. It never obtains policy
        evidence or performs Nightscout I/O itself.
        """
        from .admission_runtime import AdmissionRuntime
        with self._proof_lock:
            if (self._proof_closed.is_set() or self._proof_client is None or
                    self.identity is None or self._admission_runtime is not None):
                raise NightscoutAuthorizationError("admission_runtime_unavailable")
            root = self.config.get("authorization_admission_dir")
            if not root:
                raise NightscoutAuthorizationError("admission_storage_unavailable")
            runtime = AdmissionRuntime(self._proof_client, self.identity, evidence,
                os.path.join(root, "settings-epoch"), os.path.join(root, "key-epoch"),
                os.path.join(root, "candidates"), os.path.join(root, "committed"),
                os.path.join(root, "policy-anchor"),
                clock=self._monotonic)
            self._admission_runtime = runtime
            return runtime

    def enrollment_components(self):
        """Return no partial capability: publisher and workflow appear together."""
        with self._proof_lock:
            if (self._admission_activation_state != "active" or
                    self._admission_runtime is None):
                return None, None
            return (self._admission_runtime.challenge_publisher,
                    self._admission_runtime.reverse_workflow)

    def tls_stream_factory(self):
        """Return the current provenance-backed HTTP factory or no capability."""
        with self._proof_lock:
            if (self._admission_activation_state != "active" or
                    self._admission_runtime is None):
                return None
            return self._admission_runtime.make_tls_stream

    def recovery_registry(self):
        """Explicit internal recovery capability; no listener or route uses it."""
        with self._proof_lock:
            if (self._admission_activation_state not in ("recovery_only", "active") or
                    self._admission_runtime is None):
                return None
            return self._admission_runtime.registry

    def admitted_peer(self, credential_id):
        """Return a peer already committed by the active admission owner.

        Recovery commits are authoritative local proof for the exact key. The
        BLE shadow path may use this read-only snapshot immediately, instead of
        waiting for the legacy Nightscout v1 collection to expose a phone row.
        No network lookup, candidate promotion, or new owner is performed.
        """
        with self._proof_lock:
            if (self._admission_activation_state not in ("recovery_only", "active") or
                    self._admission_runtime is None):
                return None
            registry = self._admission_runtime.registry
            admitted = registry.active_peer(credential_id)
            if admitted is not None:
                return admitted
            # HTTP recovery and the BLE sidecar have separate runtime objects.
            # Let the sidecar consume the short-lived marker written by the
            # HTTP owner, with the durable committed archive as the authority.
            admitted = registry.recently_committed_peer(credential_id)
            if admitted is None:
                print("openaps authorization recent commit miss category=" +
                      str(registry.last_recent_commit_failure or "unknown"),
                      file=sys.stderr, flush=True)
            return admitted

    def recovery_stream_factory(self):
        """Return no route; callers must explicitly opt into this provider."""
        with self._proof_lock:
            if (self._admission_activation_state not in ("recovery_only", "active") or
                    self._admission_runtime is None):
                return None
            # The phone is the requester for /v3/recovery, so this socket
            # must be the rig witness (TLS server). The requester stream is
            # a TLS client and cannot recover against another requester.
            # Witness creation still requires an independently active peer;
            # a durable recovery-only record does not grant witness authority.
            return self._admission_runtime.make_recovery_witness_stream_from_prelude

    def admission_availability(self):
        with self._admission_activation_lock:
            return {"state": self._admission_activation_state,
                    "error_category": self._admission_activation_error_category}

    def secure_mode_capabilities(self):
        """One lock-consistent snapshot for a future all-route enforcement gate."""
        with self._admission_activation_lock:
            with self._proof_lock:
                active = (self._admission_activation_state == "active" and
                          self._admission_activation_error_category is None and
                          self._admission_runtime is not None)
                return {"state": self._admission_activation_state,
                        "error_category": self._admission_activation_error_category,
                        "tls_stream_factory": (self._admission_runtime.make_tls_stream
                            if active else None),
                        "registry": self._admission_runtime.registry if active else None}

    def _activate_admission_once(self):
        """Perform one bounded policy observation, including transient retries."""
        if not self._enable_admission:
            return False
        with self._admission_activation_lock:
            if self._admission_activation_state == "active":
                return True
            if (self._admission_activation_state == "failed" and
                    not self._admission_retryable):
                return False
            if self._admission_activation_state not in ("not_started", "recovery_only", "failed"):
                return self._admission_activation_state == "active"
            was_recovery_only = self._admission_runtime is not None
            self._admission_activation_state = "running"
        retryable_proof_step = False
        try:
            with self._proof_lock:
                if self._proof_closed.is_set() or self._proof_client is None:
                    raise NightscoutAuthorizationError("admission_runtime_unavailable")
                client = self._proof_client
            if not was_recovery_only and self.config.get("authorization_admission_dir"):
                try:
                    self.install_admission_registry(None)
                    was_recovery_only = True
                except Exception as restore_error:
                    from .reviewed_policy_anchor import PolicyAnchorMissing
                    if not isinstance(restore_error, PolicyAnchorMissing):
                        raise
            # Only the remote proof steps are retryable. Local anchor/owner
            # installation failures may be ambiguous and must remain sticky.
            retryable_proof_step = True
            observation = client.observe_enrollment_permissions()
            evidence = client.reviewed_policy_evidence(observation)
            retryable_proof_step = False
            with self._proof_lock:
                if self._proof_closed.is_set() or self._proof_client is not client:
                    raise NightscoutAuthorizationError("admission_runtime_unavailable")
                installed = self._admission_runtime
            if installed is None:
                self.install_admission_registry(evidence)
            else:
                installed.upgrade_policy(evidence)
            with self._admission_activation_lock:
                if self._admission_activation_state == "cancelled":
                    raise NightscoutAuthorizationError("admission_runtime_unavailable")
                self._admission_activation_state = "active"
                self._admission_activation_error_category = None
                self._admission_retryable = False
            print("openaps authorization admission active", file=sys.stderr, flush=True)
            return True
        except Exception as exc:
            category = (getattr(exc, "category", None) or type(exc).__name__)
            with self._admission_activation_lock:
                if self._admission_activation_state != "cancelled":
                    self._admission_activation_state = (
                        "recovery_only" if was_recovery_only and
                        self._admission_runtime is not None else "failed")
                    self._admission_activation_error_category = category
                    self._admission_retryable = retryable_proof_step
            print("openaps authorization admission unavailable category=" + category,
                  file=sys.stderr, flush=True)
            return False

    def initialize_async(self):
        if self.mode != "shadow":
            return None
        with self._initialization_lock:
            if self._initialization_inflight:
                return None
            self._initialization_inflight = True

        def run():
            try:
                self._initialize()
                if self.client is not None:
                    self._activate_admission_once()
            except Exception:
                # This is a final containment boundary for all auth-only I/O.
                self.client = None
                self.replay = None
                self.carrier_ready_cached = False
                self.last_state = {
                    "mode": self.mode,
                    "classification": "initialization_error",
                    "error_category": "unexpected",
                }
            finally:
                with self._initialization_lock:
                    self._initialization_inflight = False
            if self.client is not None:
                self.reconcile_async()

        thread = threading.Thread(target=run, name="openaps-auth-shadow-initialize")
        thread.daemon = True
        try:
            thread.start()
        except Exception:
            with self._initialization_lock:
                self._initialization_inflight = False
            self.last_state = {
                "mode": self.mode,
                "classification": "initialization_error",
                "error_category": "thread_unavailable",
            }
            return None
        return thread

    @property
    def credential_id(self):
        return self.identity.credential_id if self.identity is not None else None

    @property
    def supported(self):
        return self.identity is not None and self.client is not None

    def _state_is_carrier_ready(self, state):
        if not self.client or not isinstance(state, dict):
            return False
        capability = state.get("capability") or {}
        return bool(
            state.get("classification") == "present" and
            state.get("authority_context_id") == self.client.authority_context_id and
            state.get("credential_id") == self.credential_id and
            state.get("duplicate_state") == "one_live_non_authoritative" and
            _positive_integral_timestamp(state.get("last_registry_srv_created")) and
            _positive_integral_timestamp(state.get("last_registry_srv_modified")) and
            capability.get("supported") and
            capability.get("security_enabled") and
            capability.get("read") and
            capability.get("create")
        )

    def ensure_shadow_carrier_ready(self):
        if not self.client:
            return False
        if self.carrier_ready_cached:
            return True
        # Shadow must never put a Nightscout wait on the legacy delivery path.
        # Refresh asynchronously and let this observation be skipped.
        self.reconcile_async()
        return False

    def reconcile(self):
        if not self.client:
            return dict(self.last_state)
        try:
            reconcile_if_due = getattr(self.client, "reconcile_self_if_due", None)
            if reconcile_if_due is not None:
                self.last_state = reconcile_if_due(
                    SUCCESSFUL_SELF_RECONCILE_SECONDS,
                    FAILED_SELF_RECONCILE_THROTTLE_SECONDS,
                )
            else:
                self.last_state = self.client.reconcile_self()
            self.carrier_ready_cached = self._state_is_carrier_ready(self.last_state)
        except NightscoutAuthorizationError as exc:
            self.last_state = {
                "mode": self.mode,
                "classification": "error",
                "error_category": exc.category,
                "credential_id": self.credential_id,
            }
        except Exception:
            self.last_state = {
                "mode": self.mode,
                "classification": "error",
                "error_category": "unexpected",
                "credential_id": self.credential_id,
            }
        return dict(self.last_state)

    def reconcile_async(self):
        monotonic = getattr(self, "_monotonic", time.monotonic)
        now = monotonic()
        with self._reconcile_async_lock:
            if self._reconcile_async_inflight:
                return None
            last_started = getattr(self, "_reconcile_last_started", None)
            refresh_interval = getattr(self, "_reconcile_refresh_interval", 0)
            if (
                last_started is not None and
                now >= last_started and
                now - last_started < refresh_interval
            ):
                return None
            self._reconcile_async_inflight = True
            self._reconcile_last_started = now
            self._reconcile_refresh_interval = FAILED_SELF_RECONCILE_THROTTLE_SECONDS

        def run():
            next_interval = FAILED_SELF_RECONCILE_THROTTLE_SECONDS
            try:
                state = self.reconcile()
                if (
                    self._state_is_carrier_ready(state) or
                    state.get("classification") == "ambiguous_create"
                ):
                    next_interval = SUCCESSFUL_SELF_RECONCILE_SECONDS
            finally:
                with self._reconcile_async_lock:
                    self._reconcile_refresh_interval = next_interval
                    self._reconcile_async_inflight = False

        thread = threading.Thread(target=run, name="openaps-auth-shadow-reconcile")
        thread.daemon = True
        try:
            thread.start()
        except Exception:
            with self._reconcile_async_lock:
                self._reconcile_async_inflight = False
                self._reconcile_refresh_interval = FAILED_SELF_RECONCILE_THROTTLE_SECONDS
            self.last_state = {
                "mode": self.mode,
                "classification": "error",
                "error_category": "thread_unavailable",
                "credential_id": self.credential_id,
            }
            return None
        return thread

    def start_periodic_reconciliation(self, interval_seconds=6 * 60 * 60):
        with self._reconcile_async_lock:
            if self._periodic_reconcile_started:
                return None
            self._periodic_reconcile_started = True

        if self.client is None:
            self.initialize_async()
        else:
            self.reconcile_async()

        def periodic():
            while True:
                with self._admission_activation_lock:
                    retry_admission = self._admission_retryable
                delay = (
                    FAILED_INITIALIZATION_RETRY_SECONDS
                    if self.client is None or retry_admission
                    else interval_seconds
                )
                time.sleep(delay)
                self._periodic_reconciliation_tick()

        thread = threading.Thread(target=periodic, name="openaps-auth-shadow-periodic")
        thread.daemon = True
        try:
            thread.start()
        except Exception:
            with self._reconcile_async_lock:
                self._periodic_reconcile_started = False
            self.last_state = {
                "mode": self.mode,
                "classification": "error",
                "error_category": "thread_unavailable",
                "credential_id": self.credential_id,
            }
            return None
        return thread

    def _periodic_reconciliation_tick(self):
        if self.client is None:
            self.initialize_async()
            return
        with self._admission_activation_lock:
            retry_admission = self._admission_retryable
        if retry_admission:
            self._activate_admission_once()
        self.reconcile_async()

    def consume_replay(self, kind, credential_id, message_id, ack_digest=None):
        if self.client is None or self.replay is None:
            raise ValueError("authorization replay state is unavailable")
        return self.replay.consume(
            kind,
            self.client.authority_context_id,
            credential_id,
            message_id,
            ack_digest=ack_digest,
        )

    def lookup_peer(self, credential_id, device_kind):
        if not self.client:
            return {"classification": "legacy", "peer": None, "duplicate_state": "inconclusive"}
        # A just-completed recovery exchange has already committed the exact
        # peer key into the active admission owner. Use that local proof
        # immediately for the BLE shadow verifier; the legacy v1 Nightscout
        # collection may not expose phone rows even though the v3 record is
        # authoritative. This is read-only and never promotes a candidate.
        if device_kind == "phone" and getattr(self, "_admission_runtime", None) is not None:
            try:
                admitted = self.admitted_peer(credential_id)
            except Exception:
                admitted = None
            if isinstance(admitted, dict):
                return {
                    "classification": "present_cached",
                    "peer": admitted,
                    "duplicate_state": "one_live_admitted",
                }
        cached = self._cached_peer_result(credential_id)
        if cached.get("peer"):
            # Established trust is immediately usable offline. Refresh the
            # observational registry signal in the background at most once per
            # successful six-hour interval. Failed refreshes may retry after the
            # shorter five-minute failure throttle.
            self._refresh_cached_peer_async(
                credential_id,
                device_kind,
                cached_positive=True,
            )
            return cached
        # Unknown peers are fetched out of band. The first shadow attempt is
        # skipped; a later connection can use the Nightscout-confirmed cache.
        if self.client.carrier_ready():
            self._refresh_cached_peer_async(
                credential_id,
                device_kind,
                cached_positive=False,
            )
        else:
            self.reconcile_async()
        return cached

    def _refresh_cached_peer_async(self, credential_id, device_kind, cached_positive=False):
        monotonic = getattr(self, "_monotonic", time.monotonic)
        now = monotonic()
        initial_interval = (
            SUCCESSFUL_PEER_REFRESH_SECONDS
            if cached_positive
            else FAILED_PEER_REFRESH_THROTTLE_SECONDS
        )
        with self._lookup_lock:
            last_started = getattr(self, "_lookup_last_started", None)
            if last_started is None:
                last_started = OrderedDict()
                self._lookup_last_started = last_started
            elif not isinstance(last_started, OrderedDict):
                last_started = OrderedDict(last_started.items())
                self._lookup_last_started = last_started
            refresh_intervals = getattr(self, "_lookup_refresh_intervals", None)
            if refresh_intervals is None:
                refresh_intervals = {}
                self._lookup_refresh_intervals = refresh_intervals
            for stale in [
                key for key, started in last_started.items()
                if (
                    key not in self._lookup_inflight and
                    now - started >= refresh_intervals.get(
                        key,
                        FAILED_PEER_REFRESH_THROTTLE_SECONDS,
                    )
                )
            ]:
                last_started.pop(stale, None)
                refresh_intervals.pop(stale, None)
            if credential_id in self._lookup_inflight:
                return
            previous = last_started.get(credential_id)
            if previous is not None:
                interval = refresh_intervals.get(credential_id, initial_interval)
                if now - previous < interval:
                    last_started.pop(credential_id, None)
                    last_started[credential_id] = previous
                    return
                last_started.pop(credential_id, None)
                refresh_intervals.pop(credential_id, None)
            while len(last_started) >= MAX_PEER_REFRESH_HISTORY_ENTRIES:
                evicted = None
                for candidate in last_started:
                    if candidate not in self._lookup_inflight:
                        evicted = candidate
                        break
                if evicted is None:
                    return
                last_started.pop(evicted, None)
                refresh_intervals.pop(evicted, None)
            event = threading.Event()
            self._lookup_inflight[credential_id] = event
            last_started[credential_id] = now
            refresh_intervals[credential_id] = initial_interval

        def refresh():
            next_interval = FAILED_PEER_REFRESH_THROTTLE_SECONDS
            try:
                # The client persists positive confirmations and observational
                # absence/410/duplicate signals. Shadow mode does not revoke.
                result = self.client.lookup_peer(credential_id, device_kind)
                if result.get("classification") == "present":
                    next_interval = SUCCESSFUL_PEER_REFRESH_SECONDS
            except Exception:
                pass
            finally:
                with self._lookup_lock:
                    if credential_id in self._lookup_last_started:
                        self._lookup_refresh_intervals[credential_id] = next_interval
                        started = self._lookup_last_started.pop(credential_id)
                        self._lookup_last_started[credential_id] = started
                    self._lookup_inflight.pop(credential_id, None)
                    event.set()

        thread = threading.Thread(target=refresh, name="openaps-auth-shadow-peer-refresh")
        thread.daemon = True
        try:
            thread.start()
        except Exception:
            with self._lookup_lock:
                if credential_id in self._lookup_last_started:
                    self._lookup_refresh_intervals[
                        credential_id
                    ] = FAILED_PEER_REFRESH_THROTTLE_SECONDS
                self._lookup_inflight.pop(credential_id, None)
                event.set()
            return None
        return thread

    def _cached_peer_result(self, credential_id, duplicate_state=None):
        peer = self.client.trust.peer(credential_id) if self.client else None
        if (
            not peer or
            peer.get("authority_context_id") != getattr(self.client, "authority_context_id", None)
        ):
            return {
                "classification": "inconclusive",
                "peer": None,
                "duplicate_state": duplicate_state or "inconclusive",
            }
        public_key = peer.get("public_key_der")
        if isinstance(public_key, str):
            try:
                peer["public_key_der"] = base64.b64decode(public_key.encode("ascii"), validate=True)
            except Exception:
                return {
                    "classification": "inconclusive",
                    "peer": None,
                    "duplicate_state": duplicate_state or "inconclusive",
                }
        return {
            "classification": "present_cached",
            "peer": peer,
            "duplicate_state": duplicate_state or peer.get("registry_duplicate_state") or "inconclusive",
        }
