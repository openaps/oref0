import json
import socket
import ssl
import struct
import threading
import unittest

from openaps_locald.authorization_tls import TLSError
from openaps_locald.tls_socket import serve_tls_socket
from tests import test_tls_stream as stream_fixture


class TLSSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper_type = type("SocketStreamFixture", (stream_fixture.StreamTests,), {})
        cls.helper_type.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.helper_type.tearDownClass()

    def setUp(self):
        self.helper = self.helper_type()
        self.helper.setUp()
        self.local, self.peer = socket.socketpair()
        self.peer.settimeout(3)
        self.stream = self.helper.stream()
        self.cancel = threading.Event()
        self.outcome = []
        self.worker = None

    def tearDown(self):
        self.cancel.set()
        self.peer.close()
        if self.worker:
            self.worker.join(3)
            self.assertFalse(self.worker.is_alive())
        self.local.close()
        self.helper.tearDown()

    def start(self, **kwargs):
        def work():
            try:
                self.outcome.append(serve_tls_socket(self.local, self.stream, self.cancel.is_set, **kwargs))
            except Exception as error:
                self.outcome.append(error)
        self.worker = threading.Thread(target=work)
        self.worker.daemon = True
        self.worker.start()

    def receive_exact(self, length):
        data = b""
        while len(data) < length:
            chunk = self.peer.recv(length - len(data))
            self.assertTrue(chunk)
            data += chunk
        return data

    def handshake(self):
        fixture = self.helper.fixture
        hello = fixture.rig_hello.encode()
        self.assertEqual(self.receive_exact(len(hello)), hello)
        client, incoming, outgoing = fixture.client()
        self.peer.sendall(fixture.phone_hello.encode())
        for _ in range(64):
            ready = False
            try:
                client.do_handshake()
                ready = True
            except ssl.SSLWantReadError:
                pass
            wire = outgoing.read()
            if wire:
                self.peer.sendall(wire)
            if ready:
                return client, incoming, outgoing
            incoming.write(self.peer.recv(65536))
        self.fail("socket handshake did not settle")

    def test_real_socket_tls_clinical_read(self):
        self.clinical_read()

    def clinical_read(self):
        self.start()
        client, incoming, outgoing = self.handshake()
        request = {"schema": "openaps.tls.request.v1", "request_id": "synthetic",
                   "destination_credential_id": self.helper.fixture.rig.credential_id,
                   "method": "GET", "path": "/v1/health", "query": {}, "body": None}
        encoded = json.dumps(request).encode("utf-8")
        client.write(struct.pack("!I", len(encoded)) + encoded)
        self.peer.sendall(outgoing.read())
        response = bytearray()
        # A short-write transport may expose >64 socket fragments for a full
        # response. Keep a finite loop without depending on packet coalescing.
        for _ in range(256):
            try:
                response.extend(client.read(65536))
            except ssl.SSLWantReadError:
                incoming.write(self.peer.recv(65536))
            self.assertLessEqual(len(response), 65536)
            if len(response) >= 4 and len(response) == 4 + struct.unpack("!I", response[:4])[0]:
                break
        self.assertEqual(json.loads(response[4:].decode("utf-8"))["body"], self.helper.body)

    def test_idle_cancellation_closes_socket_and_releases_slot(self):
        self.start()
        self.receive_exact(len(self.helper.fixture.rig_hello.encode()))
        self.cancel.set()
        self.worker.join(2)
        self.assertEqual(self.outcome, ["cancelled"])
        self.assertFalse(self.helper.fixture.pool.entries)
        self.assertEqual(self.peer.recv(1), b"")

    def test_peer_eof_releases_slot(self):
        self.start()
        self.receive_exact(len(self.helper.fixture.rig_hello.encode()))
        self.peer.shutdown(socket.SHUT_WR)
        self.worker.join(2)
        self.assertEqual(self.outcome, ["eof"])
        self.assertFalse(self.helper.fixture.pool.entries)

    def test_expiry_during_wait_prevents_queued_hello_send(self):
        def poll(readers, writers, errors, timeout):
            self.assertEqual(readers, [])
            self.assertEqual(timeout, 0.5)
            self.helper.fixture.now = 20
            return [], writers, []
        self.start(poll=poll)
        self.worker.join(2)
        self.assertIsInstance(self.outcome[0], TLSError)
        self.assertEqual(self.peer.recv(1), b"")
        self.assertFalse(self.helper.fixture.pool.entries)

    def test_trust_loss_while_idle_closes_live_socket(self):
        self.start()
        self.handshake()
        self.helper.fixture.snapshot["trust_generation"] = "changed"
        self.worker.join(2)
        self.assertIsInstance(self.outcome[0], TLSError)
        self.assertFalse(self.helper.fixture.pool.entries)

    def test_partial_writes_preserve_large_encrypted_response(self):
        underlying = self.local
        attempts = []
        class ShortWrites(object):
            def __getattr__(self, name):
                return getattr(underlying, name)
            def send(self, data):
                attempts.append(len(data))
                return underlying.send(data[:997])
        self.local = ShortWrites()
        self.helper.body = {"synthetic": "x" * 65370}
        self.clinical_read()
        self.assertGreater(len(attempts), 60)
        self.assertLessEqual(max(attempts), 16384)

    def test_blocked_writer_still_expires_without_reading_input(self):
        underlying = self.local
        waits = []
        class BlockedWrites(object):
            def __getattr__(self, name):
                return getattr(underlying, name)
            def send(self, data):
                raise BlockingIOError()
        self.local = BlockedWrites()
        def poll(readers, writers, errors, timeout):
            self.assertFalse(readers)
            waits.append(True)
            if len(waits) == 2:
                self.helper.fixture.now = 20
            return [], writers, []
        self.start(poll=poll)
        self.worker.join(2)
        self.assertEqual(len(waits), 2)
        self.assertIsInstance(self.outcome[0], TLSError)
        self.assertEqual(self.peer.recv(1), b"")
        self.assertFalse(self.helper.fixture.pool.entries)


if __name__ == "__main__":
    unittest.main()
