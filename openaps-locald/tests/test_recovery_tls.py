"""Synthetic MemoryBIO tests only: no network, runtime enrollment or clinical I/O."""
import copy
import json
import os
import ssl
import struct
import tempfile
import unittest
import uuid

from openaps_locald.authorization_tls import AdmissionPool, CertificateHello, TLSError, issue_local_certificate
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.continuity import BoundContinuity, Continuity
from openaps_locald.recovery_tls import ALPN, RecoveryHello, RecoveryReservation, RecoveryTLSServer
from openaps_locald import recovery_challenge as codec


class RecoveryTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="openaps-recovery-tls-test-")
        cls.rig = DeviceIdentity(os.path.join(cls.directory.name, "rig"))
        cls.phone = DeviceIdentity(os.path.join(cls.directory.name, "phone"))
        cls.other = DeviceIdentity(os.path.join(cls.directory.name, "other"))
        cls.rig_hello = RecoveryHello(2, issue_local_certificate(cls.rig).der)
        cls.phone_hello = RecoveryHello(1, issue_local_certificate(cls.phone).der)
        cls.other_hello = RecoveryHello(1, issue_local_certificate(cls.other).der)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.now = 0.0
        self.pool = AdmissionPool(clock=lambda: self.now)
        self.authority = "ns_" + "a" * 64
        self.snapshot = {
            "authority_context_id": self.authority, "local_credential_id": self.rig.credential_id,
            "peer_credential_id": self.phone.credential_id, "connection_generation": str(uuid.uuid4()),
            "trust_generation": str(uuid.uuid4()),
            "peer": {"credential_id": self.phone.credential_id, "public_key_der": self.phone.public_key_der,
                     "device_kind": "phone", "authority_context_id": self.authority}}
        self.binding = tuple(self.snapshot[key] for key in ("authority_context_id", "local_credential_id",
            "peer_credential_id", "connection_generation", "trust_generation"))
        self.continuity = Continuity(clock=lambda: self.now)
        self.witness = BoundContinuity(self.continuity, self.binding)
        self.reservations, self.servers = [], []

    def tearDown(self):
        for server in self.servers:
            server.close()
        for reservation in self.reservations:
            reservation.transport_terminated()
        self.assertEqual(self.pool.entries, {})

    def server(self, peer_frame=None, created=None):
        token = self.pool.acquire(None)
        reservation = RecoveryReservation(self.pool, token, self.now if created is None else created,
                                           clock=lambda: self.now)
        self.reservations.append(reservation)
        server = RecoveryTLSServer(self.rig, self.rig_hello, peer_frame or self.phone_hello.encode(),
            lambda: self.snapshot, self.witness, reservation)
        self.servers.append(server)
        return server

    def client(self, protocols=(ALPN,), other=False):
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_REQUIRED
        context.verify_flags |= 0x80000 | 0x200000
        context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(self.rig_hello.der))
        context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        # Python 3.5/OpenSSL can fail while encoding an empty ALPN list. Omitting
        # the setter is the actual no-ALPN client, not a skipped handshake test.
        if protocols:
            context.set_alpn_protocols(list(protocols))
        identity, hello = (self.other, self.other_hello) if other else (self.phone, self.phone_hello)
        path = os.path.join(self.directory.name, "test-client.pem")
        with open(path, "w") as handle:
            handle.write(ssl.DER_cert_to_PEM_cert(hello.der))
        context.load_cert_chain(path, identity.private_key_path)
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        return context.wrap_bio(incoming, outgoing, server_side=False), incoming, outgoing

    def connect(self, server, client=None, fragment=20):
        client, incoming, outgoing = client or self.client()
        ready = False
        for _ in range(64):
            if not ready:
                try:
                    client.do_handshake()
                    ready = True
                except ssl.SSLWantReadError:
                    pass
            wire = outgoing.read()
            for offset in range(0, len(wire), fragment):
                self.assertIsNone(server.receive(wire[offset:offset + fragment]))
            incoming.write(server.drain_wire())
            if ready and server.ready:
                return client, incoming, outgoing
        self.fail("recovery handshake did not settle")

    def request(self):
        return codec.fresh_request(self.authority, self.phone.credential_id, "phone",
            self.rig.credential_id, "rig", uuid.uuid4())

    def test_distinct_hello_no_normal_mode_fallback(self):
        self.assertEqual(RecoveryHello.decode(self.phone_hello.encode()).public_key_der, self.phone.public_key_der)
        with self.assertRaises(TLSError):
            CertificateHello.decode(self.phone_hello.encode())
        normal = CertificateHello(1, self.phone_hello.der)
        with self.assertRaises(TLSError):
            self.server(normal.encode())

    def test_actual_tls_response_no_contact_renewal_and_terminal_reservation_release(self):
        server = self.server()
        self.now = 1
        client, incoming, outgoing = self.connect(server, fragment=1)
        request = self.request()
        self.assertNotEqual(request["connection_id"], self.binding[3])
        encoded = codec.encode_request(request)
        self.now = 2
        client.write(struct.pack("!I", len(encoded)) + encoded)
        server.receive(outgoing.read())
        incoming.write(server.drain_wire())
        response_frame = client.read()
        count = struct.unpack("!I", response_frame[:4])[0]
        self.assertEqual(count, len(response_frame) - 4)
        response = json.loads(response_frame[4:].decode("ascii"))
        self.assertEqual(codec.verify_response(request, response, self.rig.public_key_der, self.phone), 2)
        self.assertEqual(self.continuity.recent_contact_age_for_recovery(), 2)
        self.assertTrue(server.close_required)
        server.close()
        self.assertEqual(len(self.pool.entries), 1) # A close request is not terminal confirmation.
        server.reservation.transport_terminated()
        self.assertEqual(len(self.pool.entries), 0)

    def test_missing_wrong_alpn_and_wrong_handshake_key_fail_without_application(self):
        for protocols, other in [((), False), (("wrong/1",), False), ((ALPN,), True)]:
            server = self.server()
            with self.assertRaises((TLSError, ssl.SSLError)):
                self.connect(server, self.client(protocols, other))
            self.assertFalse(server.responded)
            self.assertEqual(self.continuity.recent_contact_age_for_recovery(), 0)
            server.close()
            server.reservation.transport_terminated()

    def test_generation_key_authority_changes_and_original_deadline_close_without_release(self):
        original = copy.deepcopy(self.snapshot)
        for field in ["trust_generation", "connection_generation", "authority_context_id", "peer_credential_id", "deadline"]:
            self.snapshot = copy.deepcopy(original)
            self.now = 19
            server = self.server(created=0)
            if field == "deadline":
                self.now = 20
            else:
                self.snapshot[field] = str(uuid.uuid4()) if field.endswith("generation") else "invalid"
            with self.assertRaises(TLSError):
                server.tick()
            self.assertTrue(server.closed)
            self.assertIn(server.reservation.token, self.pool.entries)
            server.reservation.transport_terminated()

    def test_wrong_request_scope_trailing_bytes_and_inherited_witness_never_respond(self):
        for mode in ["scope", "trailing", "inherited"]:
            server = self.server()
            client, incoming, outgoing = self.connect(server)
            request = self.request()
            if mode == "scope":
                request["authority_context_id"] = "ns_" + "b" * 64
            if mode == "inherited":
                server.witness = BoundContinuity(Continuity(clock=lambda: self.now, recovered_age=1), self.binding)
            data = codec.encode_request(request)
            client.write(struct.pack("!I", len(data)) + data + (b"x" if mode == "trailing" else b""))
            with self.assertRaises(TLSError):
                server.receive(outgoing.read())
            self.assertTrue(server.closed)
            server.reservation.transport_terminated()

    def test_expired_ticket_and_wrong_peer_ticket_never_parse_tls(self):
        token = self.pool.acquire(self.other.credential_id)
        reservation = RecoveryReservation(self.pool, token, 0, clock=lambda: self.now)
        self.reservations.append(reservation)
        with self.assertRaises(TLSError):
            RecoveryTLSServer(self.rig, self.rig_hello, self.phone_hello.encode(),
                lambda: self.snapshot, self.witness, reservation)
        self.assertIn(token, self.pool.entries)
        self.now = 20
        with self.assertRaises(TLSError):
            reservation.require_held()
        self.now = 0
        with self.assertRaises(TLSError):
            reservation.require_held()
