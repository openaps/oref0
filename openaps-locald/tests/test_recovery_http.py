import base64
import os
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from openaps_locald.http_api import ThreadedHTTPServer, make_handler
from openaps_locald.recovery_challenge import ChallengeError
from openaps_locald.config import default_config
from openaps_locald.install_config import build_install_config
from openaps_locald.tls_socket import serve_recovery_socket


class CompleteRecoveryStream(object):
    def __init__(self):
        self.close_required = True
        self.terminal = 0

    def tick(self):
        pass

    def drain(self, maximum):
        return b""

    def transport_terminated(self):
        self.terminal += 1
        return "synthetic-revision"


class RecoveryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="openaps-recovery-http-")
        self.server = None
        self.calls = []
        self.streams = []

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.worker.join(2)
            self.handler.db.close()
        self.directory.cleanup()

    def start(self, provider=None):
        self.handler = make_handler({
            "db_path": os.path.join(self.directory.name, "events.sqlite3"),
            "rig_id": "rig-placeholder", "patient_id": "patient-placeholder",
            "auth_token": "synthetic-token"},
            recovery_stream_factory_provider=provider)
        self.server = ThreadedHTTPServer(("127.0.0.1", 0), self.handler)
        self.worker = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02))
        self.worker.daemon = True
        self.worker.start()

    @staticmethod
    def prelude():
        return base64.b64encode(b"synthetic bounded signed prelude")

    def request(self, extra=b"", path=b"/v3/recovery", upgrade=b"openaps-recovery/1"):
        return (b"GET " + path + b" HTTP/1.1\r\nHost: example.invalid\r\n"
                b"Connection: Upgrade\r\nUpgrade: " + upgrade + b"\r\nContent-Length: 0\r\n"
                b"OpenAPS-Recovery: " + self.prelude() + b"\r\n" + extra + b"\r\n")

    def exchange(self, request):
        peer = socket.create_connection(self.server.server_address, timeout=2)
        try:
            peer.sendall(request)
            result = b""
            while b"\r\n\r\n" not in result and len(result) < 8192:
                value = peer.recv(1)
                if not value:
                    break
                result += value
            return result
        finally:
            peer.close()

    def available(self):
        self.calls.append("provider")
        def factory(prelude):
            self.calls.append(prelude)
            stream = CompleteRecoveryStream()
            self.streams.append(stream)
            return stream
        return factory

    def test_success_samples_provider_once_and_has_no_clinical_dispatch_arguments(self):
        self.start(self.available)
        response = self.exchange(self.request())
        self.assertTrue(response.startswith(b"HTTP/1.1 101"))
        self.assertIn(b"Upgrade: openaps-recovery/1", response)
        self.assertEqual(self.calls, ["provider", b"synthetic bounded signed prelude"])
        self.assertEqual(self.streams[0].terminal, 1)

    def test_unavailable_is_503_before_upgrade(self):
        calls = []
        def provider():
            calls.append(1)
            return None
        self.start(provider)
        response = self.exchange(self.request())
        self.assertIn(b" 503 ", response)
        self.assertNotIn(b" 101 ", response)
        self.assertEqual(calls, [1])

    def test_recovery_failure_logs_only_fixed_reason_and_stage(self):
        def provider():
            def factory(prelude):
                raise ChallengeError("registry peer not admitted")
            return factory
        self.start(provider)
        with patch("openaps_locald.http_api._api_log") as log:
            self.assertIn(b" 503 ", self.exchange(self.request()))
        log.assert_called_once_with(
            "recovery TLS upgrade failed category=challenge "
            "stage=before_upgrade reason=registry_peer_not_admitted")

    def test_recovery_failure_never_logs_exception_payload(self):
        def provider():
            raise ValueError("synthetic-private-payload")
        self.start(provider)
        with patch("openaps_locald.http_api._api_log") as log:
            self.assertIn(b" 503 ", self.exchange(self.request()))
        log.assert_called_once_with(
            "recovery TLS upgrade failed category=other "
            "stage=before_upgrade reason=unclassified")

    def test_route_header_body_and_oversize_ambiguity_fail_before_provider(self):
        self.start(self.available)
        requests = [
            self.request(extra=b"Host: duplicate.invalid\r\n"),
            self.request(extra=b"OpenAPS-Recovery: " + self.prelude() + b"\r\n"),
            self.request(extra=b"Transfer-Encoding: chunked\r\n"),
            self.request(extra=b"Expect: 100-continue\r\n"),
            self.request().replace(b"Content-Length: 0", b"Content-Length: 1"),
            self.request(upgrade=b"openaps-tls/1"),
            self.request().replace(self.prelude(), b"!not-base64!"),
            self.request().replace(self.prelude(), base64.b64encode(b"x" * 2049)),
        ]
        for request in requests:
            self.assertIn(b" 400 ", self.exchange(request))
        self.assertEqual(self.calls, [])

    def test_exact_route_only_and_default_off(self):
        self.start(self.available)
        for path in (b"/v3/recovery/", b"/v3/recovery?peer=x", b"/V3/recovery"):
            response = self.exchange(self.request(path=path))
            self.assertNotIn(b" 101 ", response)
        self.assertEqual(self.calls, [])

    def test_config_and_installer_keep_recovery_default_off(self):
        self.assertIs(default_config(self.directory.name)["authorization_recovery_enabled"], False)
        installed = build_install_config({}, self.directory.name, "127.0.0.1", 8787)
        self.assertIs(installed["authorization_recovery_enabled"], False)
        installed = build_install_config({"authorization_recovery_enabled": True},
                                         self.directory.name, "127.0.0.1", 8787)
        self.assertIs(installed["authorization_recovery_enabled"], True)
        additive = build_install_config(
            {}, self.directory.name, "127.0.0.1", 8787,
            enable_authorization_providers=True)
        self.assertIs(additive["authorization_admission_enabled"], True)
        self.assertIs(additive["authorization_tls_enabled"], True)
        self.assertIs(additive["authorization_recovery_enabled"], True)
        self.assertIs(additive["ble_authorization_tls_relay_enabled"], True)
        self.assertIs(additive["authorization_secure_mode_enabled"], False)
        self.assertIs(additive["ble_require_auth"], False)

    def test_socket_closes_before_terminal_callback(self):
        events = []
        class Connection(object):
            def setsockopt(self, *args):
                pass
            def setblocking(self, value):
                pass
            def close(self):
                events.append("socket-close")
        class Stream(CompleteRecoveryStream):
            def transport_terminated(inner):
                self.assertEqual(events, ["socket-close"])
                events.append("terminal")
                return "revision"
        result = serve_recovery_socket(Connection(), Stream())
        self.assertEqual(result, "revision")
        self.assertEqual(events, ["socket-close", "terminal"])


if __name__ == "__main__":
    unittest.main()
