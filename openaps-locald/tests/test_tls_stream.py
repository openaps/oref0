import copy
import json
import ssl
import struct
import unittest

from openaps_locald.authorization_tls import AdmissionPool, TLSError, TLSServer
from openaps_locald.tls_clinical import TLSClinicalSession
from openaps_locald.tls_stream import TLSStream
from tests import test_authorization_tls as fixtures


class StreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_type = type("StreamFixture", (fixtures.TLSReceiverTests,), {})
        cls.fixture_type.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_type.tearDownClass()

    def setUp(self):
        self.fixture = self.fixture_type()
        self.fixture.setUp()
        self.streams = []
        self.factories = 0
        self.body = {"synthetic": True}

    def tearDown(self):
        for stream in self.streams:
            stream.close()
        self.fixture.tearDown()

    def stream(self):
        fixture = self.fixture
        owner = self
        class Reads(object):
            def read_authenticated(self, path, query, authorize):
                authorize()
                return 200, owner.body
        def factory(frame, token):
            self.factories += 1
            server = TLSServer(fixture.rig, fixture.rig_hello, frame,
                               lambda: fixture.snapshot,
                               clock=lambda: fixture.now, wall=lambda: fixture.wall,
                               admission=fixture.pool, admission_token=token)
            fixture.servers.append(server)
            return TLSClinicalSession(server, None, Reads())
        stream = TLSStream(fixture.rig_hello, factory, fixture.pool, clock=lambda: fixture.now)
        self.streams.append(stream)
        return stream

    def connect(self, stream):
        self.assertEqual(stream.drain(65536), self.fixture.rig_hello.encode())
        client, incoming, outgoing = self.fixture.client()
        # Coalesce certificate hello and initial TLS bytes, then fragment them.
        with self.assertRaises(ssl.SSLWantReadError):
            client.do_handshake()
        wire = self.fixture.phone_hello.encode() + outgoing.read()
        for value in wire:
            stream.receive(bytes([value]))
        incoming.write(stream.drain(65536))
        ready = False
        for _ in range(64):
            if not ready:
                try:
                    client.do_handshake()
                    ready = True
                except ssl.SSLWantReadError:
                    pass
            stream.receive(outgoing.read())
            incoming.write(stream.drain(65536))
            if ready and stream.session.tls.ready:
                return client, incoming, outgoing
        self.fail("stream handshake did not settle")

    def test_fragmented_hello_tls_and_large_clinical_response(self):
        stream = self.stream()
        token = stream.token
        client, incoming, outgoing = self.connect(stream)
        self.assertIs(stream.session.tls.token, token)
        self.assertEqual(len(self.fixture.pool.entries), 1)
        self.assertEqual(self.fixture.pool.tokens, 5)
        self.body = {"synthetic": "x" * 65370}
        request = {"schema": "openaps.tls.request.v1", "request_id": "synthetic",
                   "destination_credential_id": self.fixture.rig.credential_id,
                   "method": "GET", "path": "/v1/health", "query": {}, "body": None}
        encoded = json.dumps(request).encode("utf-8")
        client.write(struct.pack("!I", len(encoded)) + encoded)
        stream.receive(outgoing.read())
        self.assertGreater(len(stream.output), 65536)
        while stream.output:
            incoming.write(stream.drain(37))
        result = bytearray()
        while True:
            try:
                result.extend(client.read(65536))
            except ssl.SSLWantReadError:
                break
        self.assertEqual(struct.unpack("!I", result[:4])[0], len(result) - 4)
        self.assertEqual(json.loads(result[4:].decode("utf-8"))["body"], self.body)

    def test_prehello_admission_rejects_before_factory(self):
        self.stream()
        self.stream()
        with self.assertRaises(TLSError):
            self.stream()
        self.assertEqual(self.factories, 0)
        self.assertEqual(len(self.fixture.pool.entries), 2)

    def test_partial_hello_deadline_releases_and_clears(self):
        stream = self.stream()
        stream.receive(b"OAPS")
        self.fixture.now = 20
        with self.assertRaises(TLSError):
            stream.tick()
        self.assertTrue(stream.closed)
        self.assertFalse(stream.pending or stream.output or self.fixture.pool.entries)

    def test_handshake_deadline_includes_hello_time(self):
        stream = self.stream()
        self.fixture.now = 19
        stream.receive(self.fixture.phone_hello.encode())
        self.fixture.now = 20
        with self.assertRaises(TLSError):
            stream.tick()
        self.assertTrue(stream.session.tls.closed)

    def test_malformed_and_oversized_input_never_reaches_factory(self):
        for wire in (b"OAPSTLS\x01\x02\x00\x01", b"OAPSTLS\x01\x01\x10\x01", b"x" * 65537):
            stream = self.stream()
            with self.assertRaises(TLSError):
                stream.receive(wire)
            self.assertTrue(stream.closed)
        self.assertEqual(self.factories, 0)

    def test_factory_failure_releases_reservation(self):
        stream = self.stream()
        self.fixture.snapshot = {}
        with self.assertRaises(TLSError):
            stream.receive(self.fixture.phone_hello.encode())
        self.assertFalse(self.fixture.pool.entries)
        self.assertTrue(stream.closed)

    def test_tick_removes_live_session_after_trust_change(self):
        stream = self.stream()
        self.connect(stream)
        self.fixture.snapshot["trust_generation"] = "changed"
        with self.assertRaises(TLSError):
            stream.tick()
        self.assertFalse(stream.output or self.fixture.pool.entries)

    def test_reservation_binding_preserves_per_peer_limit(self):
        pool = AdmissionPool(clock=lambda: 0)
        for _ in range(2):
            token = pool.acquire("synthetic-peer")
            pool.established(token)
        reserved = pool.acquire(None)
        with self.assertRaises(TLSError):
            pool.bind(reserved, "synthetic-peer")
        pool.release(reserved)
        self.assertEqual(len(pool.entries), 2)

    def test_slow_consumer_exceeding_output_cap_closes(self):
        stream = self.stream()
        client, incoming, outgoing = self.connect(stream)
        self.body = {"synthetic": "x" * 65370}
        request = {"schema": "openaps.tls.request.v1", "request_id": "synthetic",
                   "destination_credential_id": self.fixture.rig.credential_id,
                   "method": "GET", "path": "/v1/health", "query": {}, "body": None}
        encoded = json.dumps(request).encode("utf-8")
        with self.assertRaises(TLSError):
            for _ in range(4):
                client.write(struct.pack("!I", len(encoded)) + encoded)
                stream.receive(outgoing.read())
        self.assertFalse(stream.output or self.fixture.pool.entries)
        self.assertTrue(stream.closed)

    def test_disconnect_and_invalid_drain_release_admission(self):
        stream = self.stream()
        stream.receive(b"OAPS")
        stream.close()
        stream.close()
        self.assertFalse(stream.pending or stream.output or self.fixture.pool.entries)
        stream = self.stream()
        with self.assertRaises(TLSError):
            stream.drain(True)
        self.assertFalse(self.fixture.pool.entries)

    def test_clock_regression_closes_prehello_stream(self):
        stream = self.stream()
        self.fixture.now = -1
        with self.assertRaises(TLSError):
            stream.tick()
        self.assertFalse(self.fixture.pool.entries)


if __name__ == "__main__":
    unittest.main()
