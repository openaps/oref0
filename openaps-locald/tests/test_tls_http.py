import copy
import io
import json
import os
import socket
import ssl
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from openaps_locald.authorization_tls import TLSError, TLSServer
from openaps_locald.http_api import ThreadedHTTPServer, make_handler, _BoundedHeaderReader, _HeaderLimit
from openaps_locald.secure_mode import HTTP_READS, SecureModePolicy
from openaps_locald.tls_clinical import TLSClinicalSession
from openaps_locald.tls_stream import TLSStream
from tests import test_authorization_tls as tls_fixture


class TLSHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_type = type("HTTPUpgradeFixture", (tls_fixture.TLSReceiverTests,), {})
        cls.fixture_type.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_type.tearDownClass()

    def setUp(self):
        self.fixture = self.fixture_type()
        self.fixture.setUp()
        self.directory = tempfile.TemporaryDirectory(prefix="openaps-http-tls-test-")
        self.streams, self.peers = [], []
        self.calls = 0
        self.server = None

    def tearDown(self):
        for peer in self.peers:
            peer.close()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.worker.join(2)
            deadline = time.monotonic() + 2
            while self.fixture.pool.entries and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(self.fixture.pool.entries)
            self.handler.db.close()
        self.fixture.tearDown()
        self.directory.cleanup()

    def factory(self, events, reads):
        self.calls += 1
        f = self.fixture
        def session(frame, token):
            server = TLSServer(f.rig, f.rig_hello, frame, lambda: f.snapshot,
                               clock=lambda: f.now, wall=lambda: f.wall,
                               admission=f.pool, admission_token=token)
            return TLSClinicalSession(server, events, reads)
        stream = TLSStream(f.rig_hello, session, f.pool, clock=lambda: f.now)
        self.streams.append(stream)
        return stream

    def start(self, enabled=True, factory=None, provider=None, secure_mode_provider=None):
        self.handler = make_handler({"db_path": os.path.join(self.directory.name, "events.sqlite3"),
                                     "rig_id": "rig-placeholder", "patient_id": "patient-placeholder",
                                     "auth_token": "synthetic-legacy-token"},
                                    tls_stream_factory=(factory or self.factory) if enabled and provider is None else None,
                                    tls_stream_factory_provider=provider,
                                    secure_mode_policy_provider=secure_mode_provider)
        self.server = ThreadedHTTPServer(("127.0.0.1", 0), self.handler)
        self.worker = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.05))
        self.worker.daemon = True
        self.worker.start()

    def peer(self, request):
        peer = socket.create_connection(self.server.server_address, timeout=3)
        self.peers.append(peer)
        peer.sendall(request)
        return peer

    def request(self, extra=b"", path=b"/v3/tls"):
        return b"GET " + path + b" HTTP/1.1\r\nHost: example.invalid\r\nConnection: Upgrade\r\nUpgrade: openaps-tls/1\r\n" + extra + b"\r\n"

    def headers(self, peer):
        result = b""
        while b"\r\n\r\n" not in result and len(result) < 8192:
            try:
                value = peer.recv(1)
            except ConnectionResetError:
                break
            if not value:
                break
            result += value
        return result

    def test_upgrade_coalesced_hello_and_real_encrypted_health(self):
        self.start()
        f = self.fixture
        peer = self.peer(self.request() + f.phone_hello.encode())
        self.assertTrue(self.headers(peer).startswith(b"HTTP/1.1 101"))
        hello = b""
        while len(hello) < len(f.rig_hello.encode()):
            hello += peer.recv(len(f.rig_hello.encode()) - len(hello))
        self.assertEqual(hello, f.rig_hello.encode())
        client, incoming, outgoing = f.client()
        for _ in range(64):
            ready = False
            try:
                client.do_handshake()
                ready = True
            except ssl.SSLWantReadError:
                pass
            wire = outgoing.read()
            if wire:
                peer.sendall(wire)
            if ready:
                break
            incoming.write(peer.recv(65536))
        self.assertTrue(ready)
        request = {"schema": "openaps.tls.request.v1", "request_id": "synthetic",
                   "destination_credential_id": f.rig.credential_id,
                   "method": "GET", "path": "/v1/health", "query": {}, "body": None}
        data = json.dumps(request).encode("utf-8")
        client.write(struct.pack("!I", len(data)) + data)
        peer.sendall(outgoing.read())
        result = bytearray()
        for _ in range(256):
            try:
                result.extend(client.read(65536))
            except ssl.SSLWantReadError:
                incoming.write(peer.recv(65536))
            if len(result) >= 4 and len(result) == struct.unpack("!I", result[:4])[0] + 4:
                break
        response = json.loads(result[4:].decode("utf-8"))
        self.assertEqual(response["status"], 200)
        self.assertIs(response["body"]["ok"], True)

    def test_startup_default_cannot_upgrade(self):
        self.start(enabled=False)
        self.assertIn(b" 401 ", self.headers(self.peer(self.request())))
        self.assertEqual(self.calls, 0)

    def test_invalid_upgrade_body_and_duplicate_headers_rejected(self):
        self.start()
        for extra in (b"Content-Length: 1\r\n", b"Transfer-Encoding: chunked\r\n",
                      b"Expect: 100-continue\r\n", b"Upgrade: openaps-tls/1\r\n",
                      b"Host: other.invalid\r\n", b"Connection: Upgrade\r\n"):
            self.assertIn(b" 400 ", self.headers(self.peer(self.request(extra))))
        self.assertEqual(self.calls, 0)

    def test_large_header_is_closed_before_factory(self):
        self.start()
        peer = self.peer(self.request(b"X-Padding: " + b"x" * 9000 + b"\r\n"))
        self.assertNotIn(b" 101 ", self.headers(peer))
        self.assertEqual(self.calls, 0)

    def test_factory_unavailable_returns_503_without_hello(self):
        def unavailable(events, reads):
            raise TLSError("synthetic unavailable")
        self.start(factory=unavailable)
        self.assertIn(b" 503 ", self.headers(self.peer(self.request())))
        self.assertFalse(self.fixture.pool.entries)

    def test_dynamic_factory_is_sampled_once_and_fails_closed_until_complete(self):
        values = [None, object(), self.factory]
        calls = []
        def provider():
            calls.append(values[0])
            return values[0]
        self.start(enabled=False, provider=provider)
        self.assertIn(b" 503 ", self.headers(self.peer(self.request())))
        values.pop(0)
        self.assertIn(b" 503 ", self.headers(self.peer(self.request())))
        values.pop(0)
        self.assertTrue(self.headers(self.peer(self.request())).startswith(b"HTTP/1.1 101"))
        self.assertEqual(len(calls), 3)

    def test_dynamic_factory_provider_exception_is_nonclinical_503(self):
        def provider():
            raise ValueError("sensitive provider failure")
        self.start(enabled=False, provider=provider)
        self.assertIn(b" 503 ", self.headers(self.peer(self.request())))
        self.assertEqual(self.calls, 0)

    def test_failed_tls_never_falls_back_to_plaintext_http(self):
        self.start()
        peer = self.peer(self.request() + b"GET /v1/health HTTP/1.1\r\n\r\n")
        self.assertIn(b" 101 ", self.headers(peer))
        result = b""
        while True:
            try:
                value = peer.recv(65536)
            except ConnectionResetError:
                break
            if not value:
                break
            result += value
        self.assertNotIn(b"HTTP/", result)
        self.assertNotIn(b'"ok"', result)

    def test_legacy_auth_remains_required_on_other_routes(self):
        self.start()
        self.assertIn(b" 401 ", self.headers(self.peer(self.request(path=b"/v1/health"))))
        request = self.request(b"Authorization: Bearer synthetic-legacy-token\r\n", b"/v1/health")
        self.assertIn(b" 200 ", self.headers(self.peer(request)))
        self.assertEqual(self.calls, 0)

    def test_every_legacy_clinical_alias_remains_behind_legacy_auth(self):
        self.start()
        paths = (b"/v1/status", b"/v1/device-status", b"/v1/devicestatus",
                 b"/v1/materialization", b"/v1/events", b"/v1/bg-readings",
                 b"/v1/bg-readings/latest", b"/v1/pumphistory", b"/v1/pump-history",
                 b"/v1/events/synthetic", b"/v1/events/synthetic/acks")
        for path in paths:
            request = b"GET " + path + b" HTTP/1.1\r\nHost: example.invalid\r\nConnection: close\r\n\r\n"
            self.assertIn(b" 401 ", self.headers(self.peer(request)), path)
        body = b'{"events":[]}'
        request = (b"POST /v1/events HTTP/1.1\r\nHost: example.invalid\r\nConnection: close\r\n" +
                   b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
        self.assertIn(b" 401 ", self.headers(self.peer(request)))
        self.assertEqual(self.calls, 0)

    def test_secure_mode_provider_blocks_plaintext_clinical_routes_only(self):
        self.start(enabled=False,
                   secure_mode_provider=lambda: SecureModePolicy(SecureModePolicy.READY))
        auth = b"Authorization: Bearer synthetic-legacy-token\r\n"
        request = (b"GET /v1/status HTTP/1.1\r\nHost: example.invalid\r\n" +
                   auth + b"Connection: close\r\n\r\n")
        self.assertIn(b" 503 ", self.headers(self.peer(request)))

    def test_secure_mode_provider_blocks_every_legacy_clinical_alias_and_variant(self):
        self.start(enabled=False,
                   secure_mode_provider=lambda: SecureModePolicy(SecureModePolicy.READY))
        auth = b"Authorization: Bearer synthetic-legacy-token\r\n"
        paths = sorted(HTTP_READS) + [
            "/v1/events/synthetic",
            "/v1/events/synthetic/acks",
            "/v1/events/synthetic/acks?limit=1",
            "/v1/pump-history/",
            "/v1/status/?query=legacy",
        ]
        for path in paths:
            request = ("GET %s HTTP/1.1\r\nHost: example.invalid\r\n" % path).encode("ascii") + auth + b"Connection: close\r\n\r\n"
            self.assertIn(b" 503 ", self.headers(self.peer(request)), path)

        body = b'{"events":[]}'
        for path in (b"/v1/events", b"/v1/events/"):
            request = (b"POST " + path + b" HTTP/1.1\r\nHost: example.invalid\r\n" + auth +
                       b"Content-Length: " + str(len(body)).encode("ascii") +
                       b"\r\nConnection: close\r\n\r\n" + body)
            self.assertIn(b" 503 ", self.headers(self.peer(request)), path)
        request = (b"GET /v1/health HTTP/1.1\r\nHost: example.invalid\r\n" +
                   auth + b"Connection: close\r\n\r\n")
        self.assertIn(b" 200 ", self.headers(self.peer(request)))
        body = b'{"events":[]}'
        request = (b"POST /v2/events HTTP/1.1\r\nHost: example.invalid\r\n" +
                   auth + b"Content-Length: " + str(len(body)).encode("ascii") +
                   b"\r\nConnection: close\r\n\r\n" + body)
        self.assertIn(b" 503 ", self.headers(self.peer(request)))

    def test_secure_mode_provider_failure_fails_closed_for_clinical_routes(self):
        self.start(enabled=False, secure_mode_provider=lambda: None)
        auth = b"Authorization: Bearer synthetic-legacy-token\r\n"
        request = (b"GET /v1/events HTTP/1.1\r\nHost: example.invalid\r\n" +
                   auth + b"Connection: close\r\n\r\n")
        self.assertIn(b" 503 ", self.headers(self.peer(request)))
        request = (b"GET /v1/rig HTTP/1.1\r\nHost: example.invalid\r\n" +
                   auth + b"Connection: close\r\n\r\n")
        self.assertIn(b" 200 ", self.headers(self.peer(request)))

    def test_secure_mode_disabled_policy_preserves_legacy_routes(self):
        self.start(enabled=False,
                   secure_mode_provider=lambda: SecureModePolicy(SecureModePolicy.DISABLED))
        auth = b"Authorization: Bearer synthetic-legacy-token\r\n"
        request = (b"GET /v1/events HTTP/1.1\r\nHost: example.invalid\r\n" +
                   auth + b"Connection: close\r\n\r\n")
        self.assertIn(b" 200 ", self.headers(self.peer(request)))

    def test_missing_fields_and_wrong_protocol_rejected(self):
        self.start()
        request = self.request()
        for malformed in (request.replace(b"HTTP/1.1", b"HTTP/1.0"),
                          request.replace(b"Host: example.invalid\r\n", b""),
                          request.replace(b"Connection: Upgrade\r\n", b""),
                          request.replace(b"openaps-tls/1", b"unknown/1")):
            self.assertIn(b" 400 ", self.headers(self.peer(malformed)))
        self.assertEqual(self.calls, 0)

    def test_header_deadline_is_total_not_reset_per_byte(self):
        class Connection(object):
            def settimeout(self, timeout):
                pass
        source = io.BytesIO(b"ABC\r\n")
        with patch("openaps_locald.http_api.time.monotonic", side_effect=[0, 0, 6]):
            reader = _BoundedHeaderReader(source, Connection())
            with self.assertRaises(_HeaderLimit):
                reader.readline()
        self.assertEqual(source.tell(), 1)


if __name__ == "__main__":
    unittest.main()
