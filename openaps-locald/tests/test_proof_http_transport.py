import concurrent.futures
import io
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from openaps_locald.proof_http_transport import BoundedProofTransport, _WORKERS
from openaps_locald.nightscout_authorization import NightscoutAuthorizationError


class SyntheticTransport(BoundedProofTransport):
    script = "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'\\x00\\xc8{}')"
    def _command(self):
        return [sys.executable, "-c", self.script]


class ProofWorkerTests(unittest.TestCase):
    def transport(self, clock=time.monotonic):
        return SyntheticTransport("https://example.invalid", clock=clock)

    def test_bounded_worker_roundtrip_keeps_credentials_off_argv(self):
        transport = self.transport()
        transport.script = ("import json,sys; value=json.loads(sys.stdin.buffer.read().decode('utf-8')); "
            "assert len(value['bearer'])==16; sys.stdout.buffer.write(b'\\x00\\xc8{}')")
        self.assertNotIn("synthetic-secret", " ".join(transport._command()))
        self.assertEqual(transport.request_bytes("GET", "/synthetic", bearer="synthetic-secret"), (200, b"{}"))

    def test_legacy_http_requires_explicit_opt_in(self):
        with self.assertRaises(NightscoutAuthorizationError):
            SyntheticTransport("http://example.invalid:57257/base")
        transport = SyntheticTransport("http://example.invalid:57257/base", clock=time.monotonic,
            allow_insecure_http=True)
        self.assertEqual(transport.request_bytes("GET", "/synthetic"), (200, b"{}"))

    def test_suspended_deadline_kills_and_reaps_worker(self):
        calls = []
        def clock():
            calls.append(1)
            return 0 if len(calls) <= 2 else 21
        transport = self.transport(clock)
        transport.script = "import sys,time; sys.stdin.buffer.read(); time.sleep(60)"
        spawned = []
        real = subprocess.Popen
        def launch(*args, **kwargs):
            process = real(*args, **kwargs); spawned.append(process); return process
        with patch("openaps_locald.proof_http_transport.subprocess.Popen", side_effect=launch):
            with self.assertRaises(NightscoutAuthorizationError):
                transport.request_bytes("GET", "/synthetic")
        self.assertIsNotNone(spawned[0].poll())
        self.assertIsNone(transport._unreaped)

    def test_cancellation_kills_active_worker_and_prevents_reuse(self):
        transport = self.transport()
        transport.script = "import sys,time; sys.stdin.buffer.read(); time.sleep(60)"
        started = threading.Event()
        spawned = []
        real = subprocess.Popen
        def launch(*args, **kwargs):
            process = real(*args, **kwargs); spawned.append(process); started.set(); return process
        with patch("openaps_locald.proof_http_transport.subprocess.Popen", side_effect=launch):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(transport.request_bytes, "GET", "/synthetic")
                self.assertTrue(started.wait(3))
                transport.cancel()
                with self.assertRaises(NightscoutAuthorizationError):
                    future.result(timeout=4)
        self.assertIsNotNone(spawned[0].poll())
        with self.assertRaises(NightscoutAuthorizationError):
            transport.request_bytes("GET", "/synthetic")

    def test_global_capacity_and_input_bound_fail_before_spawn(self):
        transport = self.transport()
        with patch("openaps_locald.proof_http_transport.subprocess.Popen") as launch:
            with self.assertRaises(NightscoutAuthorizationError):
                transport.request_bytes("PUT", "/synthetic", body="x" * 32768)
            self.assertTrue(_WORKERS.acquire(False)); self.assertTrue(_WORKERS.acquire(False))
            try:
                with self.assertRaises(NightscoutAuthorizationError):
                    transport.request_bytes("GET", "/synthetic")
            finally:
                _WORKERS.release(); _WORKERS.release()
            launch.assert_not_called()

    def test_invalid_worker_frames_fail_closed(self):
        for value in ("b''", "b'\\x00\\xc8'+b'x'*8193", "b'\\x01\\x2e{}'", "b'\\x00\\x01{}'"):
            transport = self.transport()
            transport.script = "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(" + value + ")"
            with self.assertRaises(NightscoutAuthorizationError):
                transport.request_bytes("GET", "/synthetic")

    def test_delayed_reap_retains_capacity_then_releases_exactly_once(self):
        for kill_error in (False, True):
            times = iter([0, 0, 21])
            transport = self.transport(lambda: next(times))
            class DelayedProcess:
                finished = False
                stdin, stdout, stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
                def poll(self):
                    return 0 if self.finished else None
                def communicate(self, **kwargs):
                    raise subprocess.TimeoutExpired("synthetic", kwargs["timeout"])
                def kill(self):
                    if kill_error:
                        raise OSError("synthetic kill failure")
            process = DelayedProcess()
            with patch("openaps_locald.proof_http_transport.subprocess.Popen", return_value=process):
                with self.assertRaises(NightscoutAuthorizationError):
                    transport.request_bytes("GET", "/synthetic")
            try:
                self.assertFalse(transport.reap_cancelled_worker())
                self.assertTrue(_WORKERS.acquire(False))
                try:
                    self.assertFalse(_WORKERS.acquire(False))
                finally:
                    _WORKERS.release()
            finally:
                process.finished = True
                self.assertTrue(transport.reap_cancelled_worker())
            self.assertTrue(transport.reap_cancelled_worker())  # No over-release.
            self.assertTrue(process.stdin.closed and process.stdout.closed and process.stderr.closed)
            with self.assertRaises(NightscoutAuthorizationError):
                transport.request_bytes("GET", "/synthetic")


if __name__ == "__main__":
    unittest.main()
