import unittest
import uuid

from openaps_locald.secure_mode import BLE_CLINICAL, HTTP_READS, SecureModePolicy


class Runtime(object):
    def __init__(self, state="active", error=None, factory=True):
        self.state, self.error, self.factory = state, error, factory

    def secure_mode_capabilities(self):
        return {"state": self.state, "error_category": self.error,
                "tls_stream_factory": ((lambda events, reads: None) if self.factory else None),
                "registry": object() if self.factory else None}


class SecureModePolicyTests(unittest.TestCase):
    def config(self):
        return {"authorization_secure_mode_enabled": True,
                "authorization_admission_enabled": True,
                "authorization_tls_enabled": True,
                "ble_authorization_tls_relay_enabled": True}

    def test_default_off_preserves_compatibility_without_runtime(self):
        policy = SecureModePolicy.evaluate({}, None)
        self.assertEqual(policy.state, SecureModePolicy.DISABLED)
        with self.assertRaises(ValueError):
            policy.denies_plaintext_http("GET", "/v1/status")

    def test_enabled_requires_all_transports_and_active_runtime_atomically(self):
        for missing in ("authorization_admission_enabled", "authorization_tls_enabled",
                        "ble_authorization_tls_relay_enabled"):
            config = self.config()
            config[missing] = False
            self.assertEqual(SecureModePolicy.evaluate(config, Runtime()).state,
                             SecureModePolicy.UNAVAILABLE)
        for runtime in (None, Runtime("failed"), Runtime("recovery_only"),
                        Runtime(error="synthetic"), Runtime(factory=False)):
            self.assertEqual(SecureModePolicy.evaluate(self.config(), runtime).state,
                             SecureModePolicy.UNAVAILABLE)

    def test_ready_inventory_denies_every_http_alias_but_not_bootstrap(self):
        policy = SecureModePolicy.evaluate(self.config(), Runtime())
        self.assertEqual(policy.state, SecureModePolicy.READY)
        for path in HTTP_READS:
            self.assertTrue(policy.denies_plaintext_http("GET", path), path)
            self.assertTrue(policy.denies_plaintext_http("GET", path + "/"), path)
        for path in ("/v1/events/synthetic", "/v1/events/synthetic/acks"):
            self.assertTrue(policy.denies_plaintext_http("GET", path), path)
        for path in ("/v1/events", "/v2/events"):
            self.assertTrue(policy.denies_plaintext_http("POST", path), path)
        for method, path in (("GET", "/v1/health"), ("GET", "/v1/rig"),
                             ("GET", "/v2/auth/challenge"),
                             ("POST", "/v3/enrollment/challenge"),
                             ("POST", "/v3/enrollment/reverse")):
            self.assertFalse(policy.denies_plaintext_http(method, path), path)

    def test_ready_inventory_denies_clinical_and_cached_ble_only(self):
        policy = SecureModePolicy.evaluate(self.config(), Runtime())
        for operation in BLE_CLINICAL:
            self.assertTrue(policy.denies_legacy_ble(operation), operation)
        for operation in ("rig_info", "authorization_challenge",
                          "authorization_ack", "authorization_tls_relay"):
            self.assertFalse(policy.denies_legacy_ble(operation), operation)

    def test_contract_generation_must_match_for_both_processes(self):
        generation = uuid.uuid4()
        class Store(object):
            def __init__(self, value): self.value = value
            def load(self, binding): return self.value
        self.assertEqual(SecureModePolicy.evaluate_with_contract(
            self.config(), Runtime(), Store(generation), object(), generation).state,
            SecureModePolicy.READY)
        self.assertEqual(SecureModePolicy.evaluate_with_contract(
            self.config(), Runtime(), Store(uuid.uuid4()), object(), generation).reason,
            "generation_mismatch")
        self.assertEqual(SecureModePolicy.evaluate_with_contract(
            self.config(), Runtime(), Store(None), object(), generation).reason,
            "generation_mismatch")


if __name__ == "__main__":
    unittest.main()
