"""Synthetic phone-requester/rig-witness stream coverage."""
import json
import os
import ssl
import struct
import threading
import unittest
import uuid

from openaps_locald.admission_runtime import AdmissionRuntime
from openaps_locald.authorization_runtime import AuthorizationRuntime
from openaps_locald.authorization_tls import issue_local_certificate
from openaps_locald.recovery_tls import ALPN, RecoveryHello
from openaps_locald import recovery_challenge
from openaps_locald.recovery_http_prelude import prepare
from tests import test_admission_runtime


class RecoveryWitnessStreamTests(unittest.TestCase):
    def setUp(self):
        helper = test_admission_runtime.AdmissionRuntimeTests()
        f, client, evidence, paths = helper.fixture()
        self.addCleanup(helper.doCleanups)
        self.f = f
        self.runtime = AdmissionRuntime(client, f.rig, evidence, *paths, clock=lambda: f.time)
        self.addCleanup(self.runtime.invalidate)
        helper.complete_enrollment(f, self.runtime)

    def client(self):
        f = self.f
        phone_hello = RecoveryHello(1, issue_local_certificate(f.phone).der)
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_REQUIRED
        context.verify_flags |= 0x80000 | 0x200000
        context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(self.runtime.local_hello.der))
        context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        context.set_alpn_protocols([ALPN])
        path = os.path.join(f.directory.name, "witness-phone.pem")
        with open(path, "w") as handle:
            handle.write(ssl.DER_cert_to_PEM_cert(phone_hello.der))
        context.load_cert_chain(path, f.phone.private_key_path)
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        return phone_hello, context.wrap_bio(incoming, outgoing, server_side=False), incoming, outgoing

    def test_phone_requester_receives_rig_witness_and_releases_ticket(self):
        f = self.f
        prelude = prepare(f.phone, f.authority, f.rig.credential_id)
        # Exercise the production HTTP provider selection, not only the
        # witness implementation: selecting a requester here gives two TLS
        # clients and can never complete the handshake below.
        runtime = AuthorizationRuntime.__new__(AuthorizationRuntime)
        runtime._proof_lock = threading.RLock()
        runtime._admission_activation_state = "active"
        runtime._admission_runtime = self.runtime
        stream = runtime.recovery_stream_factory()(prelude)
        phone_hello, client, incoming, outgoing = self.client()
        self.assertEqual(RecoveryHello.decode(stream.drain(65536)).public_key_der, f.rig.public_key_der)
        stream.receive(phone_hello.encode())
        ready = False
        for _ in range(80):
            if not ready:
                try:
                    client.do_handshake(); ready = True
                except ssl.SSLWantReadError:
                    pass
            wire = outgoing.read()
            if wire:
                stream.receive(wire)
            peer_wire = stream.drain(65536)
            if peer_wire:
                incoming.write(peer_wire)
            if ready and stream.engine.ready:
                break
        self.assertTrue(ready)
        request = recovery_challenge.fresh_request(f.authority, f.phone.credential_id,
            "phone", f.rig.credential_id, "rig", uuid.uuid4())
        encoded = recovery_challenge.encode_request(request)
        frame = struct.pack("!I", len(encoded)) + encoded
        self.assertEqual(client.write(frame), len(frame))
        stream.receive(outgoing.read())
        response_wire = stream.drain(65536)
        incoming.write(response_wire)
        response_frame = client.read(4100)
        count = struct.unpack("!I", response_frame[:4])[0]
        response = json.loads(response_frame[4:].decode("ascii"))
        self.assertEqual(count, len(response_frame) - 4)
        self.assertEqual(recovery_challenge.verify_response(request, response,
            f.rig.public_key_der, f.phone), 0)
        self.assertTrue(stream.close_required)
        stream.transport_terminated()
        self.assertEqual(self.runtime.admission_pool.entries, {})


if __name__ == "__main__":
    unittest.main()
