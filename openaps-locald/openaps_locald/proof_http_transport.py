"""Deadline-owned proof HTTP subprocess. Secrets use pipes, never argv/files."""
import json
import math
import os
import struct
import subprocess
import sys
import threading

from .authorization_tls import boottime
from .nightscout_authorization import URLTransport, NightscoutAuthorizationError

_WORKERS = threading.BoundedSemaphore(2)


class BoundedProofTransport:
    def __init__(self, base_url, clock=boottime, allow_insecure_http=False):
        # Validate the unredacted authority before retaining it or spawning.
        strict = URLTransport(base_url, require_https=not allow_insecure_http,
            allow_insecure_http=allow_insecure_http, response_limit=8192)
        self._base_url = strict.base_url
        self._allow_insecure_http = bool(allow_insecure_http)
        self._clock = clock
        self._cancelled = threading.Event()
        self._operation = threading.Lock()
        self._unreaped = None

    def cancel(self):
        self._cancelled.set()

    def reap_cancelled_worker(self):
        """Nonblocking cleanup poll. Keep cancelled owners until this is True.

        False means active work or a retained child has not reached a terminal
        state. Never release capacity merely because a kill was requested.
        """
        if not self._operation.acquire(False):
            return False
        try:
            process = self._unreaped
            if process is None:
                return True
            if process.poll() is None:
                return False
            try:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            finally:
                self._unreaped = None
                _WORKERS.release()
            return True
        finally:
            self._operation.release()

    def _command(self):
        return [sys.executable, "-m", "openaps_locald.proof_http_transport"]

    def _worker_environment(self):
        # The service launcher may add this package to sys.path at runtime;
        # subprocesses do not inherit that mutation. Pin the worker to the
        # exact installed package that created it, never a stale cwd checkout.
        package_parent = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = package_parent
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment

    def request(self, method, path, **kwargs):
        status, raw = self.request_bytes(method, path, **kwargs)
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise NightscoutAuthorizationError("malformed_response") from None

    def request_bytes(self, method, path, body=None, bearer=None, query=None, api_secret=None):
        if self._cancelled.is_set() or self._unreaped is not None:
            raise NightscoutAuthorizationError("proof_transport_cancelled")
        payload = json.dumps({"base_url": self._base_url, "method": method, "path": path,
            "body": body, "bearer": bearer, "query": query, "api_secret": api_secret,
            "allow_insecure_http": self._allow_insecure_http},
            separators=(",", ":")).encode("utf-8")
        if len(payload) > 32768:
            raise NightscoutAuthorizationError("proof_request_oversized")
        if not self._operation.acquire(False):
            raise NightscoutAuthorizationError("proof_transport_busy")
        admitted = False
        process = None
        try:
            if not _WORKERS.acquire(False):
                raise NightscoutAuthorizationError("proof_worker_capacity")
            admitted = True
            started = last = self._clock()
            if not math.isfinite(started) or self._cancelled.is_set():
                raise NightscoutAuthorizationError("proof_transport_cancelled")
            process = subprocess.Popen(self._command(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True,
                env=self._worker_environment())
            pending_input = payload
            while True:
                now = self._clock()
                if self._cancelled.is_set() or not math.isfinite(now) or now < last or now - started >= 20:
                    raise NightscoutAuthorizationError("proof_worker_deadline_or_cancelled")
                last = now
                try:
                    output, _ = process.communicate(input=pending_input, timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    pending_input = None
            now = self._clock()
            if self._cancelled.is_set() or not last <= now < started + 20:
                raise NightscoutAuthorizationError("proof_worker_deadline_or_cancelled")
            if process.returncode != 0 or not 2 <= len(output) <= 8194:
                raise NightscoutAuthorizationError("proof_worker_failed")
            status = struct.unpack("!H", output[:2])[0]
            if not 100 <= status <= 599 or 300 <= status < 400:
                raise NightscoutAuthorizationError("proof_worker_invalid_status")
            return status, output[2:]
        finally:
            try:
                if process is not None and process.poll() is None:
                    try:
                        process.kill()
                        process.communicate(timeout=2)
                    except (OSError, subprocess.TimeoutExpired):
                        pass  # Terminal state, not kill success, decides release.
            finally:
                if process is not None and process.poll() is None:
                    self._unreaped = process
                    self._cancelled.set()
                if admitted and self._unreaped is None:
                    _WORKERS.release()
                self._operation.release()


def _worker():
    raw = sys.stdin.buffer.read(32769)
    if not 0 < len(raw) <= 32768:
        return 1
    try:
        request = json.loads(raw.decode("utf-8"))
        if set(request) != {"base_url", "method", "path", "body", "bearer", "query", "api_secret", "allow_insecure_http"}:
            return 1
        allow_insecure_http = request.pop("allow_insecure_http")
        if type(allow_insecure_http) is not bool:
            return 1
        transport = URLTransport(request.pop("base_url"), require_https=not allow_insecure_http,
            allow_insecure_http=allow_insecure_http, response_limit=8192)
        status, body = transport.request_bytes(**request)
        if not 100 <= status <= 599 or len(body) > 8192:
            return 1
        sys.stdout.buffer.write(struct.pack("!H", status) + body)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        # Do not serialize exception messages containing URLs or credentials.
        return 1


if __name__ == "__main__":
    sys.exit(_worker())
