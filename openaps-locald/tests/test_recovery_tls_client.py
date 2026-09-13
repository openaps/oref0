"""Explicit phone witness fixture; not a production phone recovery endpoint."""
import json
import os
import socket
import ssl
import struct
import unittest

from openaps_locald.recovery_tls_client import RecoveryTLSClient, _Completion
from openaps_locald.recovery_tls import ALPN, RecoveryReservation, RecoveryHello
from openaps_locald.recovery_exchange import RecoveryExchange
from openaps_locald.authorization_tls import TLSError
from openaps_locald import recovery_challenge as codec
from tests import test_recovery_tls


class RecoveryTLSClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_recovery_tls.RecoveryTLSTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        test_recovery_tls.RecoveryTLSTests.tearDownClass()

    def setUp(self):
        self.f = test_recovery_tls.RecoveryTLSTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.sockets = socket.socketpair()
        for sock in self.sockets:
            sock.settimeout(2)
            self.addCleanup(sock.close)

    def engine(self, frame=None, exchange=None):
        f = self.f
        exchange = exchange or RecoveryExchange(f.authority, f.rig.credential_id, "rig", f.phone.credential_id,
            "phone", f.phone.public_key_der, f.binding[3], f.rig, clock=lambda: f.now)
        reservation = RecoveryReservation(f.pool, f.pool.acquire(None), f.now, clock=lambda: f.now)
        f.reservations.append(reservation)
        engine = RecoveryTLSClient(f.rig, f.rig_hello, frame or f.phone_hello.encode(),
                                  lambda: f.snapshot, reservation, exchange)
        self.addCleanup(engine.close)
        return engine

    def fixture_server(self, protocols=(ALPN,), other=False):
        f = self.f
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_REQUIRED
        context.verify_flags |= 0x80000 | 0x200000
        context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(f.rig_hello.der))
        context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        if protocols:
            context.set_alpn_protocols(list(protocols))
        identity, hello = (f.other, f.other_hello) if other else (f.phone, f.phone_hello)
        path = os.path.join(f.directory.name, "fixture-phone-server.pem")
        with open(path, "w") as handle:
            handle.write(ssl.DER_cert_to_PEM_cert(hello.der))
        context.load_cert_chain(path, identity.private_key_path)
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        return context.wrap_bio(incoming, outgoing, server_side=True), incoming, outgoing

    def transfer(self, data, sender):
        if not data:
            return b""
        self.sockets[sender].sendall(data)
        result = b""
        while len(result) < len(data):
            result += self.sockets[1 - sender].recv(len(data) - len(result))
        return result

    def complete(self, engine, protocols=(ALPN,), other=False, extra=b"", graceful=None):
        tls, incoming, outgoing = self.fixture_server(protocols, other)
        ready = False
        request = b""
        for _ in range(64):
            incoming.write(self.transfer(engine.drain_wire(), 0))
            if not ready:
                try:
                    tls.do_handshake()
                    ready = True
                except ssl.SSLWantReadError:
                    pass
            wire = outgoing.read()
            if wire:
                engine.receive(self.transfer(wire, 1))
            if ready:
                try:
                    request += tls.read(4100)
                except ssl.SSLWantReadError:
                    pass
            if request:
                count = struct.unpack("!I", request[:4])[0]
                self.assertEqual(count, len(request) - 4)
                fields = codec.decode_request(request[4:])
                response = json.dumps(codec.signed_response(fields, self.f.phone, self.f.authority,
                                                          "phone", 100)).encode("ascii")
                tls.write(struct.pack("!I", len(response)) + response + extra)
                if graceful == "coalesced":
                    try:
                        tls.unwrap()
                    except ssl.SSLWantReadError:
                        pass
                engine.receive(self.transfer(outgoing.read(), 1))
                if graceful == "separate":
                    try:
                        tls.unwrap()
                    except ssl.SSLWantReadError:
                        pass
                    engine.receive(self.transfer(outgoing.read(), 1))
                return
        self.fail("fixture TLS did not complete")

    def test_actual_tls_completion_only_after_physical_adapter_close(self):
        engine = self.engine()
        self.complete(engine)
        self.assertTrue(engine.close_required)
        self.assertEqual(len(self.f.pool.entries), 1)
        with self.assertRaises(TLSError):
            engine.require_completion(engine._evidence)
        for sock in self.sockets:
            sock.close()  # Actual fixture transport terminal BEFORE event.
        completion = engine.transport_terminated()
        self.assertEqual(self.f.pool.entries, {})
        engine.require_completion(completion)
        with self.assertRaises(TLSError):
            _Completion(None, engine)
        with self.assertRaises(TLSError):
            engine.transport_terminated()
        self.f.snapshot["trust_generation"] = "changed"
        with self.assertRaises(TLSError):
            engine.require_completion(completion)

    def test_actual_missing_wrong_alpn_and_leaf(self):
        for protocols, other in (((), False), (("wrong/1",), False), ((ALPN,), True)):
            engine = self.engine()
            with self.assertRaises((TLSError, ssl.SSLError)):
                self.complete(engine, protocols, other)
            self.assertIsNone(engine._evidence)
            self.assertEqual(len(self.f.pool.entries), 1)
            engine.reservation.transport_terminated()

    def test_wrong_role_key_and_deadline_preserve_quota_until_terminal(self):
        for frame in (self.f.other_hello.encode(), RecoveryHello(2, self.f.phone_hello.der).encode()):
            with self.assertRaises(TLSError):
                self.engine(frame)
            self.f.reservations[-1].transport_terminated()
        engine = self.engine()
        self.f.now = 20
        with self.assertRaises(TLSError):
            engine.tick()
        self.assertEqual(len(self.f.pool.entries), 1)
        for sock in self.sockets:
            sock.close()
        with self.assertRaises(TLSError):
            engine.transport_terminated()
        self.assertEqual(self.f.pool.entries, {})

    def test_extra_frame_or_failed_close_never_yields_completion(self):
        engine = self.engine()
        with self.assertRaises(TLSError):
            self.complete(engine, extra=b"x")
        self.assertEqual(len(self.f.pool.entries), 1)
        engine.reservation.transport_terminated()
        other = self.engine()
        self.complete(other)
        other.close()  # Failed/cancelled adapter closure is not success.
        self.assertEqual(len(self.f.pool.entries), 1)
        for sock in self.sockets:
            sock.close()
        with self.assertRaises(TLSError):
            other.transport_terminated()

    def test_original_exchange_deadline_and_late_replay(self):
        f = self.f
        exchange = RecoveryExchange(f.authority, f.rig.credential_id, "rig", f.phone.credential_id,
            "phone", f.phone.public_key_der, f.binding[3], f.rig, clock=lambda: f.now)
        f.now = 19
        engine = self.engine(exchange=exchange)  # Newly created reservation cannot reset exchange.
        f.now = 20
        with self.assertRaises(TLSError):
            engine.tick()
        self.assertEqual(len(f.pool.entries), 1)
        engine.reservation.transport_terminated()
        f.now = 21
        replay = self.engine()
        self.complete(replay)
        with self.assertRaises(TLSError):
            replay.receive(b"replayed wire")
        for sock in self.sockets:
            sock.close()
        with self.assertRaises(TLSError):
            replay.transport_terminated()
        self.assertEqual(f.pool.entries, {})

    def test_graceful_close_notify_coalesced_and_separate(self):
        for mode in ("coalesced", "separate"):
            engine = self.engine()
            self.complete(engine, graceful=mode)
            self.assertTrue(engine._clean_closed)
            self.assertEqual(len(self.f.pool.entries), 1)
            for sock in self.sockets:
                sock.close()
            completion = engine.transport_terminated()
            engine.require_completion(completion)
            self.sockets = socket.socketpair()
            for sock in self.sockets:
                sock.settimeout(2)
                self.addCleanup(sock.close)

    def test_truncated_terminal_record_denies_completion(self):
        engine = self.engine()
        self.complete(engine)
        engine.receive(b"\x15\x03")
        for sock in self.sockets:
            sock.close()
        with self.assertRaises(TLSError):
            engine.transport_terminated()
