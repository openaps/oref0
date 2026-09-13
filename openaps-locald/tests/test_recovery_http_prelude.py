import json
import os
import tempfile
import threading
import unittest

from openaps_locald.admission_runtime import AdmissionRuntime
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald import recovery_http_prelude


class RecoveryHTTPPreludeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="openaps-recovery-prelude-")
        self.phone = DeviceIdentity(os.path.join(self.directory.name, "phone"))
        self.rig = DeviceIdentity(os.path.join(self.directory.name, "rig"))
        self.authority = "ns_" + "a" * 64

    def tearDown(self):
        self.directory.cleanup()

    def test_signed_canonical_prelude_verifies_exact_context_and_peer(self):
        data = recovery_http_prelude.prepare(self.phone, self.authority,
                                             self.rig.credential_id)
        nonce = recovery_http_prelude.verify(data, self.rig, self.authority,
            self.rig.credential_id, self.phone.credential_id, self.phone.public_key_der)
        self.assertIsInstance(nonce, str)
        with self.assertRaises(Exception):
            recovery_http_prelude.verify(data, self.rig, "ns_" + "b" * 64,
                self.rig.credential_id, self.phone.credential_id, self.phone.public_key_der)

    def test_tamper_trailing_and_oversize_fail_closed(self):
        data = recovery_http_prelude.prepare(self.phone, self.authority,
                                             self.rig.credential_id)
        fields = json.loads(data.decode("ascii"))
        fields["path"] = "/v3/tls"
        tampered = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("ascii")
        for invalid in (tampered, data + b" ", b"{" + b"x" * 2048):
            with self.assertRaises(Exception):
                recovery_http_prelude.shape(invalid)

    def test_expired_attempts_prune_but_live_nonce_replay_rejects(self):
        now = [0.0]
        runtime = AdmissionRuntime.__new__(AdmissionRuntime)
        runtime.clock = lambda: now[0]
        runtime._recovery_preludes = {}
        runtime._recovery_prelude_lock = threading.Lock()
        runtime.registry = type("Registry", (), {})()
        runtime.registry.identity = self.rig
        runtime.registry.scope = type("Scope", (), {"authority": self.authority})()
        class Stream(object):
            def transport_terminated(self):
                raise Exception("synthetic incomplete")
        runtime.make_recovery_stream = lambda peer, key: Stream()

        first = recovery_http_prelude.prepare(self.phone, self.authority,
                                              self.rig.credential_id)
        runtime.make_recovery_stream_from_prelude(first)
        with self.assertRaises(Exception):
            runtime.make_recovery_stream_from_prelude(first)
        for _ in range(140):
            now[0] += 21
            data = recovery_http_prelude.prepare(self.phone, self.authority,
                                                 self.rig.credential_id)
            runtime.make_recovery_stream_from_prelude(data)
        self.assertLessEqual(len(runtime._recovery_preludes), 1)


if __name__ == "__main__":
    unittest.main()
