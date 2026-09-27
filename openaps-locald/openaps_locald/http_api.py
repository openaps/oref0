from __future__ import print_function

import hashlib
import base64
import json
import os
import sys
import threading
import traceback
import socket
import time
import math
from collections import deque
try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from socketserver import ThreadingMixIn
    from urllib.parse import parse_qs, unquote, urlparse
except ImportError:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
    from SocketServer import ThreadingMixIn
    from urllib import unquote
    from urlparse import parse_qs, urlparse

from .db import EventDB
from .clinical_dispatch import ClinicalEventDispatcher, ClinicalReadDispatcher
from .device_status import read_device_status_payload
from .config import accepted_patient_ids
from .authorization_runtime import AuthorizationRuntime
from .tls_socket import serve_tls_socket, serve_recovery_socket
from .recovery_http_prelude import MAX_BYTES as MAX_RECOVERY_PRELUDE_BYTES
from .enrollment_carrier import EnrollmentPublicationWorker
from .reverse_enrollment import ReverseEnrollmentWorkflow
from .authorization_tls import TLSError, boottime
from .stored_proof import _object as _bounded_proof_object
from .write_challenge import validate_challenge
from .authorization_protocol import (
    AUTH_HELLO_SCHEMA,
    HTTP_AUTH_ATTEMPT_CAPACITY,
    HTTP_AUTH_ATTEMPT_REFILL_SECONDS,
    HTTP_CREDENTIAL_ATTEMPT_CAPACITY,
    HTTP_CREDENTIAL_REFILL_SECONDS,
    HTTP_MAX_SESSIONS_GLOBAL,
    HTTP_MAX_SESSIONS_PER_CREDENTIAL,
    HTTP_UNKNOWN_CREDENTIAL_LIMIT,
    SIGNED_EVENT_SCHEMA,
    MAX_AUTH_MESSAGE_BYTES,
    MAX_EVENT_MESSAGE_BYTES,
    AuthorizationError,
    ChallengeStore,
    SessionStore,
    TokenBucket,
    build_auth_ack,
    build_shadow_observation,
    build_signed_ack,
    validate_auth_hello_shape,
    validate_signed_event,
    verify_auth_hello,
)
from .materialize import collector_ack_details, materialize_event_result, read_materialization_state
from .pump_history import read_pumphistory_payload
from .models import ValidationError, ack, validate_event
from .status import status
from .secure_mode import HTTP_READS
from .secure_mode_runtime import SecureModeRouteOwner


def _json_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _matching_legacy_ack_bytes(acks, expected_sha256):
    matches = set()
    for persisted_ack in acks:
        if not isinstance(persisted_ack, dict):
            continue
        encoded = _json_bytes(persisted_ack)
        if hashlib.sha256(encoded).hexdigest() == expected_sha256:
            matches.add(encoded)
    if len(matches) != 1:
        raise AuthorizationError("legacy ACK observation is unavailable or ambiguous")
    return matches.pop()


# Keep relay diagnostics useful without ever copying exception text (which
# could be supplied by a lower layer) into the journal.  These are the fixed
# TLSError messages emitted by the authorization stream implementation.
_TLS_ERROR_REASONS = frozenset((
    "invalid stream clock", "invalid local hello", "invalid stream state",
    "stream handshake expired", "stream input limit", "invalid stream hello",
    "stream admission mismatch", "stream output limit", "invalid stream drain",
    "suspend-aware clock unavailable", "invalid hello", "noncanonical certificate",
    "invalid hello size", "invalid hello framing", "local certificate key mismatch",
    "invalid certificate clock", "invalid admission clock", "admission unavailable",
    "invalid admission reservation", "peer admission unavailable", "trust unavailable",
    "invalid binding", "peer rejected", "live continuity unavailable",
    "continuity expired", "TLS admission failed", "closed", "invalid session clock",
    "handshake expired", "session expired", "trust changed", "TLS certificate changed",
    "TLS session unavailable", "wire limit", "handshake limit",
    "post-handshake protocol rejected", "record limit", "TLS peer rejected",
    "peer closed", "plaintext limit", "client certificate rejected",
    "TLS input rejected", "output limit", "application write limit",
    "partial application write", "TLS write rejected", "TLS output unavailable",
))


def _tls_error_reason(error):
    """Return a bounded, static reason token for a TLS stream failure."""
    if isinstance(error, TLSError) and str(error) in _TLS_ERROR_REASONS:
        return str(error).replace(" ", "_").lower()
    return "unclassified"


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Keep slow shadow authorization off the legacy HTTP accept loop."""

    daemon_threads = True
    request_queue_size = 32

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(16)
        super(ThreadedHTTPServer, self).__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            return ThreadingMixIn.process_request(self, request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            return ThreadingMixIn.process_request_thread(self, request, client_address)
        finally:
            self._request_slots.release()


def _api_log(message):
    print("[api] %s" % message, flush=True)


def _event_summary(event):
    if not isinstance(event, dict):
        return "non-dict"
    return "event_id=%s patient_id=%s event_type=%s" % (
        event.get("event_id"),
        event.get("patient_id"),
        event.get("event_type"),
    )


def _filter_bg_events(events):
    return [event for event in events if isinstance(event, dict) and event.get("event_type") == "bg_reading"]


def _query_limit(query, default):
    raw = query.get("limit", [default])[0]
    try:
        limit = int(raw)
    except Exception:
        return default
    if limit <= 0:
        return default
    return limit


def _latest_bg_event(events):
    bg_events = _filter_bg_events(events)
    if not bg_events:
        return None
    bg_events.sort(key=lambda event: event.get("event_id") or "", reverse=True)
    return bg_events[0]


def _authorization_metadata(runtime):
    if runtime is None:
        return {"mode": "legacy", "protocol_version": None}
    credential_id = runtime.credential_id if runtime.identity is not None else None
    return {
        "mode": runtime.mode,
        "protocol_version": 1 if runtime.identity is not None else None,
        "credential_id": credential_id,
        "state": runtime.last_state.get("classification"),
    }


def _authorization_diagnostics(runtime):
    metadata = _authorization_metadata(runtime)
    credential_id = metadata.pop("credential_id", None)
    if credential_id:
        metadata["credential_id_hint"] = credential_id[:8] + "..." + credential_id[-8:]
    # This is intentionally a stable, non-secret category rather than an
    # exception message.  It lets a shadow deployment distinguish an
    # unsupported registry from a transient failure without disclosing the
    # Nightscout endpoint, token, or record contents through its local API.
    if metadata.get("state") == "error":
        metadata["error_category"] = (
            runtime.last_state.get("error_category") or
            runtime.last_state.get("last_attempt_error") or
            "unexpected"
        )
    return metadata


class _HeaderLimit(Exception):
    pass


class _BoundedHeaderReader(object):
    """Unbuffered prelude only; never prefetch public hello or clinical bytes."""
    def __init__(self, reader, connection):
        self.reader, self.connection = reader, connection
        self.remaining = 8192
        self.deadline = time.monotonic() + 5

    def readline(self, size=-1):
        result = bytearray()
        while size < 0 or len(result) < size:
            remaining_time = self.deadline - time.monotonic()
            if self.remaining <= 0 or remaining_time <= 0:
                raise _HeaderLimit()
            self.connection.settimeout(remaining_time)
            value = self.reader.read(1)
            if not value:
                break
            result.extend(value)
            self.remaining -= 1
            if value == b"\n":
                break
        return bytes(result)


def make_handler(config, authorization_runtime=None, tls_stream_factory=None, enrollment_challenge_publisher=None,
                 enrollment_clock=None, enrollment_reverse_workflow=None, enrollment_components_provider=None,
                 tls_stream_factory_provider=None, recovery_stream_factory_provider=None,
                 secure_mode_policy_provider=None):
    # This is deliberately constructor injection, not a configuration toggle.
    # Normal service startup cannot enable an unproven authorization factory.
    if tls_stream_factory is not None and not callable(tls_stream_factory):
        raise ValueError("TLS stream factory must be callable")
    if tls_stream_factory_provider is not None and not callable(tls_stream_factory_provider):
        raise ValueError("TLS stream factory provider must be callable")
    if tls_stream_factory_provider is not None and tls_stream_factory is not None:
        raise ValueError("static and dynamic TLS stream factories are mutually exclusive")
    if (recovery_stream_factory_provider is not None and
            not callable(recovery_stream_factory_provider)):
        raise ValueError("recovery stream factory provider must be callable")
    if (secure_mode_policy_provider is not None and
            not callable(secure_mode_policy_provider)):
        raise ValueError("secure mode policy provider must be callable")
    carrier_clock = enrollment_clock or boottime
    if enrollment_challenge_publisher is not None and not callable(enrollment_challenge_publisher):
        raise ValueError("publication callback required")
    if enrollment_reverse_workflow is not None and not isinstance(enrollment_reverse_workflow, ReverseEnrollmentWorkflow):
        raise ValueError("reverse enrollment workflow required")
    if enrollment_components_provider is not None and not callable(enrollment_components_provider):
        raise ValueError("enrollment components provider required")
    if enrollment_components_provider is not None and (enrollment_challenge_publisher is not None or
            enrollment_reverse_workflow is not None):
        raise ValueError("static and dynamic enrollment components are mutually exclusive")
    enrollment_worker = (EnrollmentPublicationWorker(enrollment_challenge_publisher or (lambda challenge: None), clock=carrier_clock)
                         if (enrollment_challenge_publisher is not None or enrollment_reverse_workflow is not None or
                             enrollment_components_provider is not None) else None)

    def enrollment_components():
        if enrollment_components_provider is None:
            return enrollment_challenge_publisher, enrollment_reverse_workflow
        try:
            value = enrollment_components_provider()
        except Exception:
            return None, None
        if (not isinstance(value, tuple) or len(value) != 2 or not callable(value[0]) or
                not isinstance(value[1], ReverseEnrollmentWorkflow)):
            return None, None
        return value
    db = EventDB(config["db_path"])
    http_challenges = ChallengeStore()
    http_sessions = SessionStore(
        maximum_per_credential=HTTP_MAX_SESSIONS_PER_CREDENTIAL,
        maximum_global=HTTP_MAX_SESSIONS_GLOBAL,
    )
    http_attempts = TokenBucket(
        HTTP_AUTH_ATTEMPT_CAPACITY,
        HTTP_AUTH_ATTEMPT_REFILL_SECONDS,
    )
    http_credential_attempts = {}
    http_source_attempts = {}
    http_failures = {}
    http_unknown_credentials = deque()
    http_state_lock = threading.RLock()
    dispatcher = ClinicalEventDispatcher(
        config, db, lambda event, settings: materialize_event_result(event, settings),
        lambda event, settings: collector_ack_details(event, settings), _api_log, _event_summary,
    )
    read_dispatcher = ClinicalReadDispatcher(config, db, {
        "status": lambda *args: status(*args),
        "device_status": lambda *args: read_device_status_payload(*args),
        "materialization": lambda *args: read_materialization_state(*args),
        "pump_history": lambda *args, **kwargs: read_pumphistory_payload(*args, **kwargs),
        "metadata": lambda: _authorization_metadata(authorization_runtime),
        "diagnostics": lambda: _authorization_diagnostics(authorization_runtime),
        "latest_bg": _latest_bg_event, "query_limit": _query_limit,
    }, dispatcher.lock)
    http_shadow_slots = threading.BoundedSemaphore(
        max(1, int(config.get("authorization_http_max_inflight") or 2))
    )

    def secure_mode_clinical_path(method, path):
        normalized = path.rstrip("/") or "/"
        return ((method == "POST" and normalized in ("/v1/events", "/v2/events")) or
                (method == "GET" and (normalized in HTTP_READS or
                 normalized.startswith("/v1/events/"))))

    def secure_mode_blocks_plaintext(method, path):
        """Return whether an explicitly supplied policy blocks this request.

        The provider is an injection seam for the future cross-process
        supervisor.  With no provider, legacy compatibility is unchanged.
        An unavailable or malformed supplied policy fails closed for clinical
        routes while leaving bootstrap and operational routes reachable.
        """
        if secure_mode_policy_provider is None:
            return False
        if not secure_mode_clinical_path(method, path):
            return False
        try:
            policy = secure_mode_policy_provider()
        except Exception:
            return True
        if policy is None:
            return True
        if getattr(policy, "state", None) == "disabled":
            return False
        if getattr(policy, "state", None) == "ready":
            try:
                return bool(policy.denies_plaintext_http(method, path))
            except Exception:
                return True
        return True

    def prune_buckets(mapping, now, maximum_age=300):
        for key in [key for key, bucket in mapping.items() if now - bucket.last >= maximum_age]:
            mapping.pop(key, None)

    def recent_failures(source, now):
        with http_state_lock:
            failures = http_failures.get(source, deque())
            while failures and now - failures[0] >= 300:
                failures.popleft()
            if failures:
                http_failures[source] = failures
            else:
                http_failures.pop(source, None)
            return failures

    def record_failure(source):
        with http_state_lock:
            now = http_attempts.monotonic()
            failures = recent_failures(source, now)
            failures.append(now)
            http_failures[source] = failures

    class Handler(BaseHTTPRequestHandler):
        server_version = "openaps-locald/0.1"
        rbufsize = 0 if (tls_stream_factory is not None or tls_stream_factory_provider is not None or
                         recovery_stream_factory_provider is not None or
                         enrollment_worker is not None) else -1

        def handle_one_request(self):
            self._carrier_started = carrier_clock() if enrollment_worker is not None else None
            if (tls_stream_factory is None and tls_stream_factory_provider is None and
                    recovery_stream_factory_provider is None and enrollment_worker is None):
                return super(Handler, self).handle_one_request()
            original = self.rfile
            previous_timeout = self.connection.gettimeout()
            self.rfile = _BoundedHeaderReader(original, self.connection)
            self._tls_header_reader = (original, previous_timeout)
            try:
                return super(Handler, self).handle_one_request()
            except (_HeaderLimit, socket.timeout):
                self.close_connection = True
            finally:
                self._restore_header_reader()

        def _restore_header_reader(self):
            saved = getattr(self, "_tls_header_reader", None)
            if saved is not None:
                self.rfile = saved[0]
                self._tls_header_reader = None
                try:
                    self.connection.settimeout(saved[1])
                except OSError:
                    pass

        def parse_request(self):
            try:
                return super(Handler, self).parse_request()
            finally:
                # The body and upgraded stream are not HTTP header bytes.
                self._restore_header_reader()

        def _http_tls_upgrade(self):
            self.close_connection = True
            fields = ("Host", "Connection", "Upgrade", "Content-Length")
            if (self.request_version != "HTTP/1.1" or
                    any(len(self.headers.get_all(name, [])) > 1 for name in fields) or
                    not self.headers.get("Host") or
                    self.headers.get("Connection", "").lower() != "upgrade" or
                    self.headers.get("Upgrade", "").lower() != "openaps-tls/1" or
                    self.headers.get("Content-Length", "0") != "0" or
                    self.headers.get("Transfer-Encoding") is not None or
                    self.headers.get("Expect") is not None):
                self._send_json(400, {"error": "invalid_tls_upgrade"})
                return
            stream = None
            upgraded = False
            try:
                factory = tls_stream_factory
                if tls_stream_factory_provider is not None:
                    factory = tls_stream_factory_provider()
                if not callable(factory):
                    raise ValueError("TLS stream factory unavailable")
                # Must return an already-reserved stream using cached,
                # provenance-backed authorization; no network lookup here.
                stream = factory(dispatcher, read_dispatcher)
                stream.tick()
                self.connection.settimeout(5)
                self.protocol_version = "HTTP/1.1"
                upgraded = True
                _api_log("authorization TLS upgrade accepted")
                self.send_response_only(101)
                self.send_header("Connection", "Upgrade")
                self.send_header("Upgrade", "openaps-tls/1")
                self.end_headers()
                self.wfile.flush()
                serve_tls_socket(self.connection, stream)
            except Exception as exc:
                phase = getattr(stream, "phase", "unknown") if stream is not None else "pre_stream"
                _api_log("authorization TLS upgrade failed category=%s phase=%s reason=%s input_bytes=%d output_bytes=%d handshake_bytes=%d handshake_calls=%d handshake_want_read=%d tls_input_pending=%d tls_output_pending=%d" %
                         (type(exc).__name__, phase, _tls_error_reason(exc),
                          int(getattr(stream, "input_bytes", 0) or 0),
                          int(getattr(stream, "output_bytes", 0) or 0),
                          int(getattr(stream, "handshake_bytes", 0) or 0),
                          int(getattr(stream, "handshake_calls", 0) or 0),
                          int(getattr(stream, "handshake_want_read", 0) or 0),
                          int(getattr(stream, "tls_input_pending", 0) or 0),
                          int(getattr(stream, "tls_output_pending", 0) or 0)))
                # After switching protocols, never inject a plaintext HTTP
                # error into the authenticated stream or fall back to v1.
                if not upgraded:
                    self._send_json(503, {"error": "authorization_unavailable"})
            finally:
                if stream is not None:
                    stream.close()

        def _http_recovery_upgrade(self):
            self.close_connection = True
            fields = ("Host", "Connection", "Upgrade", "Content-Length", "OpenAPS-Recovery")
            if (self.request_version != "HTTP/1.1" or
                    any(len(self.headers.get_all(name, [])) != 1 for name in fields) or
                    not self.headers.get("Host") or
                    self.headers.get("Connection", "").lower() != "upgrade" or
                    self.headers.get("Upgrade", "").lower() != "openaps-recovery/1" or
                    self.headers.get("Content-Length") != "0" or
                    self.headers.get("Transfer-Encoding") is not None or
                    self.headers.get("Expect") is not None):
                self._send_json(400, {"error": "invalid_recovery_upgrade"})
                return
            encoded = self.headers.get("OpenAPS-Recovery", "")
            try:
                if len(encoded) > 2732 or not encoded:
                    raise ValueError("recovery prelude size")
                prelude = base64.b64decode(encoded.encode("ascii"), validate=True)
                if (not prelude or len(prelude) > MAX_RECOVERY_PRELUDE_BYTES or
                        base64.b64encode(prelude).decode("ascii") != encoded):
                    raise ValueError("recovery prelude encoding")
            except (ValueError, TypeError, UnicodeError):
                self._send_json(400, {"error": "invalid_recovery_upgrade"})
                return
            stream = None
            upgraded = False
            adapter_owned = False
            try:
                factory = recovery_stream_factory_provider()
                if not callable(factory):
                    raise ValueError("recovery stream factory unavailable")
                stream = factory(prelude)
                stream.tick()
                self.connection.settimeout(5)
                self.protocol_version = "HTTP/1.1"
                # From the first protocol-switch write onward, never append a
                # plaintext HTTP error or fall back to a legacy dispatcher.
                upgraded = True
                self.send_response_only(101)
                self.send_header("Connection", "Upgrade")
                self.send_header("Upgrade", "openaps-recovery/1")
                self.end_headers()
                self.wfile.flush()
                adapter_owned = True
                outcome = serve_recovery_socket(self.connection, stream)
                terminal = outcome if outcome in ("eof", "cancelled") else (
                    "completed" if outcome is not None else "none")
                engine = getattr(stream, "engine", None)
                _api_log("authorization recovery terminal outcome=%s ready=%s responded=%s close_required=%s" % (
                    terminal, bool(getattr(engine, "ready", False)),
                    bool(getattr(engine, "responded", False)),
                    bool(getattr(stream, "close_required", False))))
            except Exception as exc:
                frames = traceback.extract_tb(sys.exc_info()[2])
                last = frames[-1] if frames else None
                site = "%s:%d" % (os.path.basename(last.filename), last.lineno) if last else "unknown"
                engine = getattr(stream, "engine", None)
                _api_log("authorization recovery failed category=%s site=%s ready=%s responded=%s close_required=%s" % (
                    type(exc).__name__, site, bool(getattr(engine, "ready", False)),
                    bool(getattr(engine, "responded", False)),
                    bool(getattr(stream, "close_required", False))))
                if not upgraded:
                    self._send_json(503, {"error": "authorization_unavailable"})
            finally:
                if stream is not None and not adapter_owned:
                    try:
                        self.connection.close()
                    finally:
                        try:
                            stream.transport_terminated()
                        except Exception:
                            pass

        def _carrier_status(self, code, payload=None):
            self.close_connection = True
            data = _json_bytes(payload) if code == 200 and payload is not None else b""
            if len(data) > 1024:
                code, data = 503, b""
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            if data:
                self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            if data:
                self.wfile.write(data)

        def _http_enrollment_challenge(self, reverse=False):
            self.close_connection = True
            publisher, workflow = enrollment_components()
            dynamic_incomplete = (enrollment_components_provider is not None and
                (publisher is None or workflow is None))
            if (enrollment_worker is None or dynamic_incomplete or (reverse and workflow is None) or
                    (not reverse and publisher is None)):
                self._carrier_status(503)
                return
            endpoint = "/v3/enrollment/reverse" if reverse else "/v3/enrollment/challenge"
            if (self.path != endpoint or self.request_version != "HTTP/1.1" or
                    any(len(self.headers.get_all(name, [])) != 1 for name in ("Host", "Content-Length", "Content-Type")) or
                    not self.headers.get("Host") or
                    self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json" or
                    any(self.headers.get(name) is not None for name in
                        ("Transfer-Encoding", "Expect", "Authorization", "Proxy-Authorization", "Cookie"))):
                self._carrier_status(400)
                return
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or len(length) > 4 or not 0 < int(length) <= 4096 or str(int(length)) != length:
                self._carrier_status(400)
                return
            with http_state_lock:
                allowed = http_attempts.consume()
            if not allowed or not http_shadow_slots.acquire(False):
                self._carrier_status(429)
                return
            deadline = self._carrier_started + 20
            try:
                now = carrier_clock()
                if not math.isfinite(now) or now < self._carrier_started:
                    self._carrier_status(503)
                    return
                body_deadline = min(deadline, now + 5)
                last_body = now
                data = bytearray()
                try:
                    while len(data) < int(length):
                        now = carrier_clock()
                        if not math.isfinite(now) or now < last_body:
                            raise ValueError("body clock")
                        last_body = now
                        remaining = body_deadline - now
                        if remaining <= 0:
                            raise ValueError("body deadline")
                        self.connection.settimeout(remaining)
                        part = self.rfile.read(int(length) - len(data))
                        if not part:
                            raise ValueError("truncated body")
                        data.extend(part)
                    challenge = _bounded_proof_object(bytes(data), maximum_bytes=4096, maximum_depth=2 if reverse else 1)
                    if not reverse:
                        challenge = validate_challenge(challenge)
                        if challenge["peer_device_kind"] != "rig" or challenge["verifier_device_kind"] != "phone":
                            raise ValueError("carrier role")
                except Exception:
                    self._carrier_status(400)
                    return
                # Only an own-publication callback, never a peer proof result or
                # clinical dispatcher. Callback return values are discarded.
                payload = None
                if reverse:
                    code, result = enrollment_worker.execute(
                        lambda: workflow.handle(challenge, started_at=self._carrier_started), deadline)
                    if code == 202:
                        code, payload = result
                else:
                    code, _ = enrollment_worker.execute(lambda: publisher(dict(challenge)), deadline)
                self.connection.settimeout(max(0.001, min(2, deadline - carrier_clock())))
                self._carrier_status(code, payload)
            finally:
                http_shadow_slots.release()

        def log_message(self, fmt, *args):
            return

        def _send_json(self, code, payload):
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _require_secure_mode(self, method, path):
            if not secure_mode_blocks_plaintext(method, path):
                return True
            self._send_json(503, {"error": "secure_mode_required"})
            return False

        def _read_json(self, maximum_bytes=MAX_EVENT_MESSAGE_BYTES):
            length = int(self.headers.get("Content-Length") or "0")
            if length < 0 or length > maximum_bytes:
                raise ValueError("request body is too large")
            data = self.rfile.read(length)
            if not data:
                return {}
            return json.loads(data.decode("utf-8"))

        def _source_id(self):
            return self.client_address[0] if self.client_address else "unknown"

        @staticmethod
        def _credential_hint(value):
            if not isinstance(value, str) or len(value) < 16:
                return "invalid"
            return value[:8] + "..." + value[-8:]

        def _admit_http_authentication(self, credential_id, is_known):
            with http_state_lock:
                source = self._source_id()
                now = http_attempts.monotonic()
                if len(recent_failures(source, now)) >= 3:
                    raise AuthorizationError("source authentication limit reached")
                if not http_attempts.consume():
                    raise AuthorizationError("rig authentication limit reached")
                if not is_known:
                    while http_unknown_credentials and now - http_unknown_credentials[0][0] >= 300:
                        http_unknown_credentials.popleft()
                    credential_ids = set(item[1] for item in http_unknown_credentials)
                    if credential_id not in credential_ids:
                        if len(credential_ids) >= HTTP_UNKNOWN_CREDENTIAL_LIMIT:
                            raise AuthorizationError("unknown credential limit reached")
                        http_unknown_credentials.append((now, credential_id))
                prune_buckets(http_source_attempts, now)
                source_bucket = http_source_attempts.get(source)
                if source_bucket is None:
                    if len(http_source_attempts) >= 128:
                        raise AuthorizationError("source admission table is full")
                    source_bucket = TokenBucket(6, 10)
                    http_source_attempts[source] = source_bucket
                if not source_bucket.consume():
                    raise AuthorizationError("source authentication rate limit reached")
                prune_buckets(http_credential_attempts, now)
                credential_bucket = http_credential_attempts.get(credential_id)
                if credential_bucket is None:
                    if len(http_credential_attempts) >= 128:
                        raise AuthorizationError("credential admission table is full")
                    credential_bucket = TokenBucket(
                        HTTP_CREDENTIAL_ATTEMPT_CAPACITY,
                        HTTP_CREDENTIAL_REFILL_SECONDS,
                    )
                    http_credential_attempts[credential_id] = credential_bucket
                if not credential_bucket.consume():
                    raise AuthorizationError("credential authentication limit reached")

        def _http_challenge(self):
            if authorization_runtime is None or authorization_runtime.identity is None:
                self._send_json(503, {"error": "authorization_unavailable"})
                return
            source = self._source_id()
            with http_state_lock:
                now = http_attempts.monotonic()
                prune_buckets(http_source_attempts, now)
                source_bucket = http_source_attempts.get(source)
                if source_bucket is None:
                    if len(http_source_attempts) >= 128:
                        self._send_json(429, {"error": "authorization_busy"})
                        return
                    source_bucket = TokenBucket(6, 10)
                    http_source_attempts[source] = source_bucket
                if not source_bucket.consume():
                    self._send_json(429, {"error": "authorization_busy"})
                    return
                challenge = http_challenges.issue(source)
            self._send_json(200, {
                "schema": "openaps.http.auth-challenge.v1",
                "authorization_protocol_version": 1,
                "rig_credential_id": authorization_runtime.credential_id,
                "rig_challenge": challenge,
                "challenge_expires_in_seconds": 300,
                "authorization_mode": "shadow",
            })

        def _http_auth_session(self, message):
            source = self._source_id()
            try:
                if authorization_runtime is None or authorization_runtime.identity is None or authorization_runtime.client is None:
                    raise AuthorizationError("authorization shadow is unavailable")
                if not isinstance(message, dict) or message.get("schema") != AUTH_HELLO_SCHEMA:
                    raise AuthorizationError("auth hello is invalid")
                validate_auth_hello_shape(message)
                if message.get("rig_credential_id") != authorization_runtime.credential_id:
                    raise AuthorizationError("auth hello destination mismatch")
                with http_state_lock:
                    http_challenges.validate(source, message.get("rig_challenge"))
                credential_id = message.get("phone_credential_id")
                cached_peer = authorization_runtime.client.trust.peer(credential_id)
                self._admit_http_authentication(credential_id, cached_peer is not None)
                if not authorization_runtime.ensure_shadow_carrier_ready():
                    raise AuthorizationError("authorization carrier is unavailable")
                lookup = authorization_runtime.lookup_peer(credential_id, "phone")
                peer = lookup.get("peer")
                if lookup.get("classification") not in ("present", "present_cached") or not peer:
                    raise AuthorizationError("phone enrollment was not confirmed")
                verify_auth_hello(
                    message,
                    authorization_runtime.credential_id,
                    peer["public_key_der"],
                    authorization_runtime.identity,
                )
                authorization_runtime.consume_replay(
                    "hello",
                    credential_id,
                    message.get("message_id"),
                )
                with http_state_lock:
                    http_challenges.consume(source, message.get("rig_challenge"))
                    session_id = http_sessions.create(
                        credential_id,
                        authorization_runtime.credential_id,
                        connection_id=source,
                    )
                response = build_auth_ack(
                    authorization_runtime.identity,
                    message,
                    session_id=session_id,
                )
                authorization_runtime.client.trust.record_direct_contact(credential_id)
                with http_state_lock:
                    http_failures.pop(source, None)
                _api_log(
                    "authorization shadow HTTP hello verified phone=%s duplicate=%s"
                    % (self._credential_hint(credential_id), lookup.get("duplicate_state"))
                )
                self._send_json(200, response)
            except AuthorizationError:
                record_failure(source)
                self._send_json(401, {"error": "authorization_failed"})
            except Exception:
                record_failure(source)
                self._send_json(503, {"error": "authorization_unavailable"})

        def _http_signed_event(self, message):
            try:
                if authorization_runtime is None or authorization_runtime.identity is None or authorization_runtime.client is None:
                    raise AuthorizationError("authorization shadow is unavailable")
                if not isinstance(message, dict) or message.get("schema") != SIGNED_EVENT_SCHEMA:
                    raise AuthorizationError("signed event is invalid")
                credential_id = message.get("sender_credential_id")
                if message.get("destination_credential_id") != authorization_runtime.credential_id:
                    raise AuthorizationError("signed event destination mismatch")
                with http_state_lock:
                    http_sessions.require(
                        message.get("session_id"),
                        credential_id,
                        authorization_runtime.credential_id,
                        connection_id=self._source_id(),
                        nonce=message.get("message_nonce"),
                    )
                public_key = authorization_runtime.identity.load_cached_peer_public_key(credential_id)
                payload_bytes = validate_signed_event(
                    message,
                    public_key,
                    authorization_runtime.identity,
                )
                event = json.loads(payload_bytes.decode("utf-8"))
                if not isinstance(event, dict) or event.get("event_id") != message.get("message_id"):
                    raise AuthorizationError("signed event message identifier mismatch")
                validated = validate_event(event)
                if validated.get("patient_id") not in accepted_patient_ids(config):
                    raise AuthorizationError("signed event patient is not accepted")
                canonical_event = json.loads(validated["json"])
                # Read the persisted legacy result under only EventDB's short
                # SQLite lock. Shadow observation must never queue delivery on
                # the legacy materialization lock.
                persisted_event, persisted_acks = db.get_event_and_acks(
                    validated["event_id"]
                )
                if persisted_event is None:
                    raise AuthorizationError("legacy event observation is unavailable")
                persisted_validated = validate_event(persisted_event)
                if persisted_validated["json"] != validated["json"]:
                    raise AuthorizationError("signed event does not match persisted legacy event")
                legacy_ack_bytes = _matching_legacy_ack_bytes(
                    persisted_acks,
                    message.get("legacy_ack_sha256"),
                )
                authorization_runtime.consume_replay(
                    "event",
                    credential_id,
                    validated.get("event_id"),
                    ack_digest=message.get("legacy_ack_sha256"),
                )
                observation = build_shadow_observation(
                    canonical_event,
                    message,
                    legacy_ack_bytes,
                )
                with http_state_lock:
                    http_sessions.consume_nonce(
                        message.get("session_id"),
                        credential_id,
                        authorization_runtime.credential_id,
                        message.get("message_nonce"),
                        connection_id=self._source_id(),
                    )
                response = build_signed_ack(
                    authorization_runtime.identity,
                    message.get("session_id"),
                    credential_id,
                    validated.get("event_id"),
                    message.get("message_nonce"),
                    _json_bytes(observation),
                )
                authorization_runtime.client.trust.record_direct_contact(credential_id)
                self._send_json(200, response)
            except AuthorizationError:
                self._send_json(401, {"error": "authorization_failed"})
            except Exception:
                self._send_json(400, {"error": "invalid_signed_event"})

        def _authorized(self):
            token = config.get("auth_token")
            if not token:
                return True
            return self.headers.get("Authorization") == "Bearer " + token

        def _require_auth(self):
            if self._authorized():
                return True
            self._send_json(401, {"error": "unauthorized"})
            return False

        def _process_events(self, events, log_prefix="POST /v1/events"):
            return dispatcher.process_legacy(events, log_prefix)

        def do_GET(self):
            if self.path == "/v3/recovery" and recovery_stream_factory_provider is not None:
                self._http_recovery_upgrade()
                return
            if self.path == "/v3/tls" and (tls_stream_factory is not None or tls_stream_factory_provider is not None):
                self._http_tls_upgrade()
                return
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            if path == "/v2/auth/challenge":
                if not self._require_auth():
                    return
                self._http_challenge()
                return
            if not self._require_auth():
                return
            if not self._require_secure_mode("GET", path):
                return
            self._send_json(*read_dispatcher.read_legacy(path, query))

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if not self._require_secure_mode("POST", path):
                return
            if path == "/v3/enrollment/challenge":
                self._http_enrollment_challenge()
                return
            if path == "/v3/enrollment/reverse":
                self._http_enrollment_challenge(reverse=True)
                return
            if path == "/v2/auth/session":
                if not self._require_auth():
                    return
                if not http_shadow_slots.acquire(False):
                    self._send_json(429, {"error": "authorization_busy"})
                    return
                try:
                    try:
                        body = self._read_json(maximum_bytes=MAX_AUTH_MESSAGE_BYTES)
                    except Exception:
                        self._send_json(400, {"error": "invalid_auth_hello"})
                        return
                    self._http_auth_session(body)
                finally:
                    http_shadow_slots.release()
                return
            if path == "/v2/events":
                if not self._require_auth():
                    return
                if not http_shadow_slots.acquire(False):
                    self._send_json(429, {"error": "authorization_busy"})
                    return
                try:
                    try:
                        body = self._read_json(maximum_bytes=MAX_EVENT_MESSAGE_BYTES)
                    except Exception:
                        self._send_json(400, {"error": "invalid_signed_event"})
                        return
                    self._http_signed_event(body)
                finally:
                    http_shadow_slots.release()
                return
            if not self._require_auth():
                return
            if path != "/v1/events":
                self._send_json(404, {"error": "not_found"})
                return
            try:
                body = self._read_json()
            except Exception as e:
                self._send_json(400, {"error": "invalid_json", "details": str(e)})
                return
            events = body.get("events")
            if not isinstance(events, list):
                self._send_json(400, {"error": "events must be a list"})
                return
            # Materialization includes read-modify-write filesystem and process
            # control operations that were serialized by HTTPServer before v2
            # shadow handling became threaded. Preserve that legacy invariant.
            with dispatcher.lock:
                acks = self._process_events(events)
            self._send_json(200, {"acks": acks})

    Handler.db = db
    Handler.clinical_dispatcher = dispatcher
    Handler.clinical_reads = read_dispatcher
    return Handler


def serve(config):
    admission_enabled = config.get("authorization_admission_enabled") is True
    print("openaps authorization admission configured=" + str(admission_enabled).lower(),
          file=sys.stderr, flush=True)
    authorization_runtime = AuthorizationRuntime(
        config,
        initialize_in_background=True,
        enable_admission=admission_enabled,
    )
    authorization_runtime.start_periodic_reconciliation()
    secure_mode_owner = (SecureModeRouteOwner(
        config, authorization_runtime, "http")
        if config.get("authorization_secure_mode_enabled") is True else None)
    if secure_mode_owner is not None:
        secure_mode_owner.start()
    handler = make_handler(config, authorization_runtime=authorization_runtime,
        enrollment_components_provider=authorization_runtime.enrollment_components,
        tls_stream_factory_provider=(authorization_runtime.tls_stream_factory
            if config.get("authorization_tls_enabled") is True else None),
        recovery_stream_factory_provider=(authorization_runtime.recovery_stream_factory
            if config.get("authorization_recovery_enabled") is True else None),
        secure_mode_policy_provider=(secure_mode_owner.policy
            if secure_mode_owner is not None else None))
    server = ThreadedHTTPServer((config["bind_host"], config["port"]), handler)
    try:
        server.serve_forever()
    finally:
        if secure_mode_owner is not None:
            secure_mode_owner.close()
        authorization_runtime.close_proof_owner()
        handler.db.close()
