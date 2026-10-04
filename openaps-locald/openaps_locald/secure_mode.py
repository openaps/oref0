"""Atomic readiness decision for secure-only clinical transport.

The policy itself is pure and does not own process coordination. HTTP and BLE
route owners consume it only after the shared signed readiness bus has proven
one exact startup generation for both processes.
"""
from __future__ import print_function


HTTP_READS = frozenset((
    "/v1/status", "/v1/device-status", "/v1/devicestatus", "/v1/maintenance",
    "/v1/materialization", "/v1/events", "/v1/bg-readings",
    "/v1/bg-readings/latest", "/v1/pumphistory", "/v1/pump-history",
))
BLE_CLINICAL = frozenset((
    "event_write", "event_ack", "status", "pump_history", "device_status",
    "bg_readings",
))


class SecureModePolicy(object):
    DISABLED = "disabled"
    READY = "ready"
    UNAVAILABLE = "unavailable"

    def __init__(self, state, reason=None):
        if state not in (self.DISABLED, self.READY, self.UNAVAILABLE):
            raise ValueError("invalid secure-mode state")
        self.state, self.reason = state, reason

    @classmethod
    def evaluate(cls, config, authorization_runtime):
        if config.get("authorization_secure_mode_enabled") is not True:
            return cls(cls.DISABLED)
        required = ("authorization_admission_enabled", "authorization_tls_enabled",
                    "ble_authorization_tls_relay_enabled")
        missing = [key for key in required if config.get(key) is not True]
        if missing:
            return cls(cls.UNAVAILABLE, "missing_transport_gate")
        if authorization_runtime is None:
            return cls(cls.UNAVAILABLE, "missing_runtime")
        try:
            capabilities = authorization_runtime.secure_mode_capabilities()
        except Exception:
            return cls(cls.UNAVAILABLE, "runtime_error")
        if (not isinstance(capabilities, dict) or capabilities.get("state") != "active" or
                capabilities.get("error_category") is not None or
                not callable(capabilities.get("tls_stream_factory")) or
                capabilities.get("registry") is None):
            return cls(cls.UNAVAILABLE, "inactive_admission")
        return cls(cls.READY)

    @classmethod
    def evaluate_with_contract(cls, config, authorization_runtime, contract_store,
                               binding, expected_generation):
        policy = cls.evaluate(config, authorization_runtime)
        if policy.state != cls.READY:
            return policy
        try:
            observed = contract_store.load(binding)
        except Exception:
            return cls(cls.UNAVAILABLE, "contract_unavailable")
        if observed != expected_generation:
            return cls(cls.UNAVAILABLE, "generation_mismatch")
        return policy

    def require_ready(self):
        if self.state != self.READY:
            raise ValueError("secure mode is not atomically ready")

    def denies_plaintext_http(self, method, path):
        self.require_ready()
        normalized = path.rstrip("/") or "/"
        return ((method == "POST" and normalized in ("/v1/events", "/v2/events")) or
                (method == "GET" and (normalized in HTTP_READS or
                 normalized.startswith("/v1/events/"))))

    def denies_legacy_ble(self, operation):
        self.require_ready()
        return operation in BLE_CLINICAL
