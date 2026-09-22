from __future__ import print_function

import copy
import os
import ssl
import tempfile
import unittest

from openaps_locald.device_identity import DeviceIdentity, _run_openssl
from openaps_locald.continuity import Continuity, BoundContinuity
from openaps_locald.authorization_tls import (
    AdmissionPool, CertificateHello, LocalCertificateStore, TLSError, TLSServer,
    issue_local_certificate,
)


class TLSReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="openaps-tls-test-")
        cls.rig = DeviceIdentity(os.path.join(cls.directory.name, "rig"))
        cls.phone = DeviceIdentity(os.path.join(cls.directory.name, "phone"))
        cls.rig_hello = cls.certificate(cls.rig, 2)
        cls.phone_hello = cls.certificate(cls.phone, 1)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    @staticmethod
    def certificate(identity, role):
        der = _run_openssl([identity.openssl_path, "req", "-new", "-x509", "-key",
                           identity.private_key_path, "-subj", "/CN=example.invalid",
                           "-days", "1", "-set_serial", str(int.from_bytes(os.urandom(8), "big")),
                           "-outform", "DER"], lock_path=identity.openssl_lock_path)
        return CertificateHello(role, der, openssl_path=identity.openssl_path)

    def setUp(self):
        self.now = 0.0
        self.wall = 1800000000.0
        self.pool = AdmissionPool(clock=lambda: self.now)
        authority = "ns_" + "a" * 64
        self.snapshot = {
            "authority_context_id": authority, "local_credential_id": self.rig.credential_id,
            "peer_credential_id": self.phone.credential_id,
            "connection_generation": "synthetic-connection", "trust_generation": "synthetic-generation",
            "peer": {"credential_id": self.phone.credential_id,
                     "public_key_der": self.phone.public_key_der, "device_kind": "phone",
                     "authority_context_id": authority,
                     "last_nightscout_confirmed_at": self.wall - 30 * 86400,
                     "last_direct_contact_at": self.wall - 30}}
        self.snapshot["continuity"] = self.continuity(30)
        self.servers = []

    def continuity(self, age):
        binding = tuple(self.snapshot[name] for name in ("authority_context_id", "local_credential_id",
            "peer_credential_id", "connection_generation", "trust_generation"))
        return BoundContinuity(Continuity(clock=lambda: self.now, recovered_age=age), binding)

    def tearDown(self):
        for server in self.servers:
            server.close()
        self.assertEqual(len(self.pool.entries), 0)

    def server(self, hello=None):
        server = TLSServer(self.rig, self.rig_hello, (hello or self.phone_hello).encode(),
                           lambda: self.snapshot, clock=lambda: self.now,
                           wall=lambda: self.wall, admission=self.pool)
        self.servers.append(server)
        return server

    def client(self, hello=None):
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_REQUIRED
        context.verify_flags |= 0x80000 | 0x200000
        context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(self.rig_hello.der))
        context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        path = os.path.join(self.directory.name, "phone-cert.pem")
        with open(path, "w") as handle:
            handle.write(ssl.DER_cert_to_PEM_cert((hello or self.phone_hello).der))
        context.load_cert_chain(path, self.phone.private_key_path)
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
                self.assertEqual(server.receive(wire[offset:offset + fragment]), b"")
            incoming.write(server.drain_wire())
            if ready and server.ready:
                return client, incoming, outgoing
        self.fail("handshake did not settle")

    def test_fragmented_encrypted_roundtrip(self):
        server = self.server()
        client, incoming, outgoing = self.connect(server, fragment=1)
        client.write(b"synthetic request")
        wire = outgoing.read()
        self.assertNotIn(b"synthetic request", wire)
        self.assertEqual(server.receive(wire), b"synthetic request")
        server.write(b"synthetic reply")
        incoming.write(server.drain_wire())
        self.assertEqual(client.read(), b"synthetic reply")

    def test_production_non_ca_rig_certificate_roundtrip(self):
        original = self.rig_hello
        try:
            self.rig_hello = issue_local_certificate(self.rig)
            text = _run_openssl([self.rig.openssl_path, "x509", "-inform", "DER", "-text", "-noout"],
                                input_bytes=self.rig_hello.der,
                                lock_path=self.rig.openssl_lock_path)
            self.assertIn(b"CA:FALSE", text)
            self.assertNotIn(b"CA:TRUE", text)
            server = self.server()
            client, _, outgoing = self.connect(server)
            client.write(b"synthetic")
            self.assertEqual(server.receive(outgoing.read()), b"synthetic")
        finally:
            self.rig_hello = original

    def test_certificate_cache_renewal_preserves_identity(self):
        store = LocalCertificateStore(clock=lambda: self.now)
        first = store.get(self.rig)
        self.assertIs(store.get(self.rig), first)
        self.now = 86400
        renewed = store.get(self.rig)
        self.assertNotEqual(first.der, renewed.der)
        self.assertEqual(first.credential_id, renewed.credential_id)
        self.assertEqual(renewed.public_key_der, self.rig.public_key_der)
        replacement = store.get(self.phone)
        self.assertEqual(replacement.public_key_der, self.phone.public_key_der)
        self.assertNotEqual(replacement.credential_id, renewed.credential_id)

    def test_hello_shape_and_canonical_der(self):
        frame = self.phone_hello.encode()
        self.assertEqual(CertificateHello.decode(frame).public_key_der, self.phone.public_key_der)
        for invalid in (b"", frame + b"x", b"OTHER!!" + frame[7:], frame[:8] + b"\x03" + frame[9:],
                        frame[:9] + b"\xff\xff" + frame[11:], b"x" * 4108):
            with self.assertRaises(Exception):
                CertificateHello.decode(invalid)
        with self.assertRaises(Exception):
            CertificateHello(1, self.phone_hello.der + b"x")

    def test_renewal_same_enrolled_key(self):
        renewed = self.certificate(self.phone, 1)
        self.assertNotEqual(renewed.der, self.phone_hello.der)
        self.connect(self.server(renewed), self.client(renewed))

    def test_certificate_substitution_after_hello(self):
        renewed = self.certificate(self.phone, 1)
        server = self.server()
        with self.assertRaises(TLSError) as rejected:
            self.connect(server, self.client(renewed))
        self.assertIn(str(rejected.exception), ("TLS peer rejected", "client certificate rejected"))
        self.assertTrue(server.closed)

    def test_wrong_key_and_role_release_admission(self):
        for hello in (self.rig_hello, CertificateHello(2, self.phone_hello.der)):
            with self.assertRaises(TLSError) as rejected:
                self.server(hello)
            self.assertEqual(str(rejected.exception), "peer rejected")
            self.assertEqual(len(self.pool.entries), 0)

    def test_early_write_closes(self):
        server = self.server()
        with self.assertRaises(TLSError):
            server.write(b"early")
        self.assertTrue(server.closed)

    def test_trust_change_during_handshake(self):
        server = self.server()
        self.snapshot["trust_generation"] = "changed"
        with self.assertRaises(TLSError):
            self.connect(server)

    def test_trust_removal_blocks_plaintext(self):
        server = self.server()
        client, _, outgoing = self.connect(server)
        client.write(b"never released")
        self.snapshot = None
        with self.assertRaises(TLSError):
            server.receive(outgoing.read())
        self.assertTrue(server.closed)

    def test_replay_and_tampering(self):
        for tamper in (False, True):
            server = self.server()
            client, _, outgoing = self.connect(server)
            client.write(b"synthetic")
            wire = outgoing.read()
            if tamper:
                wire = wire[:-1] + bytes([wire[-1] ^ 1])
            else:
                self.assertEqual(server.receive(wire), b"synthetic")
            with self.assertRaises(TLSError):
                server.receive(wire)

    def test_handshake_deadline_and_clock_regression(self):
        for ticks in (20, -1):
            self.now = 0
            server = self.server()
            self.now = ticks
            with self.assertRaises(TLSError):
                server.tick()
            self.assertTrue(server.closed)
            self.pool.last = None

    def test_idle_and_absolute_expiry(self):
        server = self.server()
        self.connect(server)
        self.now = 299
        server.receive(b"\x16")  # Raw wire cannot renew the lease.
        self.now = 300
        with self.assertRaises(TLSError):
            server.tick()
        server = self.server()
        self.connect(server)
        for tick in range(500, 2100, 200):
            self.now = tick
            server.write(b"activity")
            server.drain_wire()
        self.now = 2100
        with self.assertRaises(TLSError):
            server.write(b"expired")

    def test_record_and_output_bounds(self):
        server = self.server()
        server.receive(b"\x16\x03")
        with self.assertRaises(TLSError):
            server.receive(b"\x03\xff\xff")
        server = self.server()
        self.connect(server)
        server.write(b"x" * 65536)
        with self.assertRaises(TLSError):
            server.write(b"x" * 65536)

    def test_admission_and_cancel_cleanup(self):
        first, second = self.server(), self.server()
        with self.assertRaises(TLSError):
            self.server()
        first.close()
        third = self.server()
        third.close()
        second.close()
        self.assertEqual(len(self.pool.entries), 0)

    def test_stale_and_cross_authority_trust_rejected(self):
        saved = copy.deepcopy(self.snapshot)
        for field, value in (("authority_context_id", "foreign"), ("device_kind", "rig")):
            self.snapshot = copy.deepcopy(saved)
            self.snapshot["peer"][field] = value
            with self.assertRaises(TLSError):
                self.server()

    def test_timestamp_only_snapshot_cannot_authorize_tls(self):
        del self.snapshot["continuity"]
        self.snapshot["peer"]["last_direct_contact_at"] = self.wall + 100
        with self.assertRaises(TLSError):
            self.server()

    def test_continuity_invalidation_closes_retained_snapshot_session(self):
        server = self.server()
        self.connect(server)
        retained = self.snapshot["continuity"]
        retained.invalidate()
        retained.invalidate()
        with self.assertRaises(TLSError):
            server.tick()
        self.assertTrue(server.closed)
        with self.assertRaises(TLSError):
            self.server()

    def test_live_continuity_expiry_closes_tls_despite_wall_clock(self):
        continuity_now = [0]
        binding = tuple(self.snapshot[name] for name in ("authority_context_id", "local_credential_id",
            "peer_credential_id", "connection_generation", "trust_generation"))
        self.snapshot["continuity"] = BoundContinuity(Continuity(clock=lambda: continuity_now[0]), binding)
        server = self.server()
        self.connect(server)
        continuity_now[0] = 86400
        self.now = 1
        self.wall -= 86400
        with self.assertRaises(TLSError):
            server.tick()
        self.assertTrue(server.closed)

    def test_normal_tls_handshake_renews_exact_scoped_contact(self):
        self.now = 100
        server = self.server()
        self.connect(server)
        self.now = 86450
        self.snapshot["continuity"].require_current(server.binding)
        self.now = 86500
        from openaps_locald.continuity import ContinuityError
        with self.assertRaises(ContinuityError):
            self.snapshot["continuity"].require_current(server.binding)

    def test_post_handshake_protocol_rejected(self):
        server = self.server()
        self.connect(server)
        with self.assertRaises(TLSError):
            server.receive(b"\x16\x03\x03\x00\x01\x00")
        self.assertTrue(server.closed)

    def test_global_admission_and_rate_bounds(self):
        pool = AdmissionPool(clock=lambda: self.now)
        tokens = []
        for index in range(8):
            self.now += 10
            token = pool.acquire("synthetic-peer-%d" % index)
            pool.established(token)
            tokens.append(token)
        with self.assertRaises(TLSError):
            pool.acquire("extra")
        for token in tokens:
            pool.release(token)
        self.assertEqual(pool.entries, {})
        pool = AdmissionPool(clock=lambda: self.now)
        for _ in range(6):
            pool.release(pool.acquire("same"))
        with self.assertRaises(TLSError):
            pool.acquire("same")
        self.now += 10
        pool.release(pool.acquire("same"))

    def test_established_peer_limit_and_trust_change_write(self):
        first, second = self.server(), self.server()
        self.connect(first)
        self.connect(second)
        with self.assertRaises(TLSError):
            self.server()
        self.snapshot["trust_generation"] = "replaced"
        with self.assertRaises(TLSError):
            first.write(b"blocked")
        self.assertTrue(first.closed)


if __name__ == "__main__":
    unittest.main()
