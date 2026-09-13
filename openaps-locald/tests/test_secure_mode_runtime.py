import os
import tempfile
import time
import unittest
import uuid

from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.secure_mode import SecureModePolicy
from openaps_locald.secure_mode_runtime import (
    HEARTBEAT_TTL_MS, SecureModeRouteOwner, decode_status, encode_status,
)
from openaps_locald.secure_mode_supervisor import Scope


class Registry(object):
    def __init__(self, scope):
        # Match the production AdmissionRegistry scope shape (which calls the
        # key epoch ``local_key_generation`` rather than ``key_epoch``).
        self.scope = type("LiveScope", (), {
            "authority": scope.authority,
            "local_credential_id": scope.local_credential_id,
            "settings_epoch": scope.settings_epoch,
            "local_key_generation": scope.key_epoch,
            "policy_generation": scope.policy_generation,
            "policy_review_sha256": scope.policy_review_sha256,
        })()


class Runtime(object):
    def __init__(self, identity, scope):
        self.identity = identity
        self.registry = Registry(scope)

    def secure_mode_capabilities(self):
        return {"state": "active", "error_category": None,
                "tls_stream_factory": lambda events, reads: None,
                "registry": self.registry}


class SecureModeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="secure-mode-runtime-")
        identity_dir = os.path.join(self.root.name, "identity")
        os.mkdir(identity_dir, 0o700)
        self.identity = DeviceIdentity(identity_dir)
        self.now = [int(time.time() * 1000)]
        self.scope = Scope(
            "ns_" + "a" * 64, self.identity.credential_id, uuid.uuid4(),
            uuid.uuid4(), uuid.uuid4(), "b" * 64)
        self.config = {
            "authorization_secure_mode_enabled": True,
            "authorization_admission_enabled": True,
            "authorization_tls_enabled": True,
            "ble_authorization_tls_relay_enabled": True,
            "authorization_secure_mode_dir": os.path.join(self.root.name, "secure"),
        }
        runtime = Runtime(self.identity, self.scope)
        self.http = SecureModeRouteOwner(self.config, runtime, "http",
                                         clock=lambda: self.now[0])
        self.ble = SecureModeRouteOwner(self.config, runtime, "ble",
                                        clock=lambda: self.now[0])

    def tearDown(self):
        self.http.close()
        self.ble.close()
        self.root.cleanup()

    def advance(self, milliseconds):
        self.now[0] += milliseconds

    def coordinate(self):
        for _index in range(6):
            self.http.tick()
            self.ble.tick()
        self.assertEqual(self.http.policy().state, SecureModePolicy.READY)
        self.assertEqual(self.ble.policy().state, SecureModePolicy.READY)

    def test_two_processes_publish_arm_commit_and_consume_exact_generation(self):
        self.assertEqual(self.http.policy().state, SecureModePolicy.UNAVAILABLE)
        self.coordinate()
        self.assertEqual(self.http.policy().reason, None)
        self.assertEqual(self.ble.policy().reason, None)

    def test_stale_or_aborted_owner_fails_closed(self):
        self.coordinate()
        self.advance(HEARTBEAT_TTL_MS + 1)
        self.assertEqual(self.http.policy().state, SecureModePolicy.UNAVAILABLE)
        self.assertEqual(self.http.policy().reason, "owner_not_armed")
        self.now[0] -= HEARTBEAT_TTL_MS + 1
        self.http.tick(); self.ble.tick()
        self.http.close()
        self.assertEqual(self.ble.policy().state, SecureModePolicy.UNAVAILABLE)

    def test_new_instances_replace_only_a_valid_old_signed_generation(self):
        self.coordinate()
        old_http = self.http
        old_ble = self.ble
        old_http.close(); old_ble.close()
        runtime = Runtime(self.identity, self.scope)
        http = SecureModeRouteOwner(self.config, runtime, "http",
                                    clock=lambda: self.now[0])
        ble = SecureModeRouteOwner(self.config, runtime, "ble",
                                   clock=lambda: self.now[0])
        try:
            for _index in range(8):
                http.tick(); ble.tick()
            self.assertEqual(http.policy().state, SecureModePolicy.READY)
            self.assertNotEqual(http.instance, old_http.instance)
        finally:
            http.close(); ble.close()

    def test_status_signature_and_canonical_encoding_are_required(self):
        data = encode_status("http", self.http.instance, self.scope, "ready",
                             self.now[0], self.identity)
        status = decode_status(data, self.identity, expected_role="http")
        self.assertEqual(status.scope, self.scope)
        self.assertEqual(status.instance, self.http.instance)
        with self.assertRaises(Exception):
            decode_status(data.replace(b"ready", b"armed"), self.identity,
                          expected_role="http")

    def test_malformed_owner_status_is_sticky_unavailable(self):
        self.coordinate()
        self.http._stores["http"].replace(b"not-json")
        self.assertFalse(self.http.tick())
        self.assertEqual(self.http.policy().state, SecureModePolicy.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
