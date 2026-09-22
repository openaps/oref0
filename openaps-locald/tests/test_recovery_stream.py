"""Internal recovery stream factory; no listener, route or clinical dispatch."""
import json
import os
import ssl
import struct
import tempfile
import unittest
import uuid
from unittest.mock import patch

from openaps_locald.admission_runtime import AdmissionRuntime
from openaps_locald.authorization_tls import CertificateHello, TLSError, issue_local_certificate
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.recovery_tls import ALPN, RecoveryHello
from openaps_locald import recovery_challenge
from openaps_locald import recovery_http_prelude
from tests import test_admission_runtime


class RecoveryStreamTests(unittest.TestCase):
    def fixture(self):
        helper = test_admission_runtime.AdmissionRuntimeTests()
        f, client, evidence, paths = helper.fixture()
        self.addCleanup(helper.doCleanups)
        fresh = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        helper.complete_enrollment(f, fresh)
        fresh.invalidate()
        runtime = AdmissionRuntime(client, f.rig, None, *paths, clock=lambda: f.time)
        self.addCleanup(runtime.invalidate)
        return f, runtime

    def phone_server(self, f, runtime):
        hello = RecoveryHello(1, issue_local_certificate(f.phone).der)
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_REQUIRED
        context.verify_flags |= 0x80000 | 0x200000
        context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(runtime.local_hello.der))
        context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        context.set_alpn_protocols([ALPN])
        directory = tempfile.TemporaryDirectory(prefix="openaps-runtime-recovery-peer-")
        self.addCleanup(directory.cleanup)
        path = os.path.join(directory.name, "phone.pem")
        with open(path, "w") as handle:
            handle.write(ssl.DER_cert_to_PEM_cert(hello.der))
        context.load_cert_chain(path, f.phone.private_key_path)
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        return hello, context.wrap_bio(incoming, outgoing, server_side=True), incoming, outgoing

    def complete(self, f, runtime, stream):
        hello, tls, incoming, outgoing = self.phone_server(f, runtime)
        offered = stream.drain(65536)
        self.assertEqual(RecoveryHello.decode(offered).public_key_der, f.rig.public_key_der)
        stream.receive(hello.encode())
        ready, request = False, b""
        for _ in range(80):
            wire = stream.drain(65536)
            if wire:
                incoming.write(wire)
            if not ready:
                try:
                    tls.do_handshake(); ready = True
                except ssl.SSLWantReadError:
                    pass
            peer_wire = outgoing.read()
            if peer_wire:
                stream.receive(peer_wire)
            if ready:
                try:
                    request += tls.read(4100)
                except ssl.SSLWantReadError:
                    pass
            if request:
                count = struct.unpack("!I", request[:4])[0]
                fields = recovery_challenge.decode_request(request[4:])
                self.assertEqual(count, len(request) - 4)
                response = json.dumps(recovery_challenge.signed_response(
                    fields, f.phone, f.authority, "phone", 100),
                    sort_keys=True, separators=(",", ":")).encode("ascii")
                tls.write(struct.pack("!I", len(response)) + response)
                try:
                    tls.unwrap()
                except ssl.SSLWantReadError:
                    pass
                stream.receive(outgoing.read())
                self.assertTrue(stream.engine.close_required)
                final = stream.drain(65536)
                if final:
                    incoming.write(final)
                return stream.attempt.connection
        self.fail("recovery stream did not settle")

    def test_success_commits_then_only_fresh_normal_connection_is_admitted(self):
        f, runtime = self.fixture()
        with patch("openaps_locald.admission_runtime.TLSClinicalSession",
                   side_effect=AssertionError("clinical dispatcher entered")):
            stream = runtime.make_recovery_stream(f.phone.credential_id, f.phone.public_key_der)
            before = runtime.committed_storage.load()
            connection = self.complete(f, runtime, stream)
            revision = stream.transport_terminated()
        self.assertIsInstance(revision, uuid.UUID)
        self.assertTrue(stream.closed)
        self.assertEqual(runtime.admission_pool.entries, {})
        self.assertNotEqual(runtime.committed_storage.load(), before)
        with self.assertRaises(Exception):
            runtime.registry.snapshot(f.phone.credential_id, connection)
        snapshot = runtime.registry.snapshot(f.phone.credential_id, str(uuid.uuid4()))
        self.assertEqual(snapshot["trust_generation"], str(revision))
        normal = runtime.make_tls_stream(object(), object())
        self.addCleanup(normal.close)
        normal.drain(65536)
        normal.receive(CertificateHello(1, issue_local_certificate(f.phone).der).encode())
        self.assertIsNotNone(normal.session)

    def test_signed_http_prelude_selects_only_exact_committed_peer_and_replays_fail(self):
        f, runtime = self.fixture()
        data = recovery_http_prelude.prepare(f.phone, f.authority,
                                             f.rig.credential_id)
        stream = runtime.make_recovery_stream_from_prelude(data)
        def cleanup():
            if not stream.closed:
                try:
                    stream.transport_terminated()
                except Exception:
                    pass
        self.addCleanup(cleanup)
        with self.assertRaises(Exception):
            runtime.make_recovery_stream_from_prelude(data)
        other = DeviceIdentity(os.path.join(f.directory.name, "prelude-other"))
        wrong = recovery_http_prelude.prepare(other, f.authority,
                                              f.rig.credential_id)
        with self.assertRaises(Exception):
            runtime.make_recovery_stream_from_prelude(wrong)

    def test_wrong_peer_capacity_and_cancel_retain_shared_quota_until_terminal(self):
        f, runtime = self.fixture()
        other = DeviceIdentity(os.path.join(f.directory.name, "recovery-other"))
        with self.assertRaises(Exception):
            runtime.make_recovery_stream(f.phone.credential_id, other.public_key_der)
        self.assertEqual(runtime.admission_pool.entries, {})

        stream = runtime.make_recovery_stream(f.phone.credential_id, f.phone.public_key_der)
        with self.assertRaises(Exception):
            runtime.make_recovery_stream(f.phone.credential_id, f.phone.public_key_der)
        self.assertEqual(len(runtime.admission_pool.entries), 1)
        stream.drain(65536)
        with self.assertRaises(TLSError):
            stream.receive(b"x" * 11)
        self.assertEqual(len(runtime.admission_pool.entries), 1)
        with self.assertRaises(TLSError):
            stream.transport_terminated()
        self.assertEqual(runtime.admission_pool.entries, {})

        one = runtime.admission_pool.acquire(None)
        two = runtime.admission_pool.acquire(None)
        with self.assertRaises(Exception):
            runtime.make_recovery_stream(f.phone.credential_id, f.phone.public_key_der)
        runtime.admission_pool.release(one)
        runtime.admission_pool.release(two)
        self.assertEqual(runtime.admission_pool.entries, {})

    def test_timeout_and_oversized_input_close_without_early_quota_release(self):
        for mode in ("timeout", "oversized"):
            f, runtime = self.fixture()
            stream = runtime.make_recovery_stream(f.phone.credential_id, f.phone.public_key_der)
            stream.drain(65536)
            if mode == "timeout":
                f.time += 20
                operation = stream.tick
            else:
                operation = lambda: stream.receive(b"x" * 65537)
            with self.assertRaises(TLSError):
                operation()
            self.assertEqual(len(runtime.admission_pool.entries), 1)
            with self.assertRaises(TLSError):
                stream.transport_terminated()
            self.assertEqual(runtime.admission_pool.entries, {})


if __name__ == "__main__":
    unittest.main()
