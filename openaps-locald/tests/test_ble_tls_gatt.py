from __future__ import print_function

import base64
import json
import tempfile
import threading
import time
import unittest

from openaps_locald.ble_protocol import (
    BleProtocolError, MAX_TLS_RELAY_FRAME_BYTES, decode_tls_relay_frame,
    encode_tls_relay_frame,
)
from openaps_locald.ble_server import BLUEZ_DEVICE_IFACE, RigBridge
from openaps_locald.ble_tls_relay import BLETLSRelayError
from openaps_locald.secure_mode import SecureModePolicy


class Runtime(object):
    mode = "legacy"
    identity = None
    credential_id = None
    client = None
    carrier_ready_cached = False
    last_state = {"classification": "legacy"}


class FakeRelay(object):
    def __init__(self, origin, timeout, fail=False):
        self.origin = origin
        self.timeout = timeout
        self.fail = fail
        self.opened = False
        self.closed = False
        self.sent = []
        self.incoming = []

    def open(self):
        if self.fail:
            raise BLETLSRelayError("synthetic unavailable")
        self.opened = True
        return self

    def send(self, value):
        if self.closed:
            raise BLETLSRelayError("closed")
        self.sent.append(value)

    def receive(self, maximum, timeout=None, timeout_is_empty=False):
        if self.closed or not self.incoming:
            if timeout_is_empty and not self.closed:
                time.sleep(min(timeout or 0, 0.01))
                return None
            raise BLETLSRelayError("unavailable")
        value = self.incoming.pop(0)
        if len(value) > maximum:
            raise AssertionError("bridge requested an unbounded read")
        return value

    def close(self):
        self.closed = True


class RelayFactory(object):
    def __init__(self, fail=False):
        self.fail = fail
        self.instances = []

    def __call__(self, origin, timeout):
        relay = FakeRelay(origin, timeout, self.fail)
        self.instances.append(relay)
        return relay


class BLETLSGATTTests(unittest.TestCase):
    def wait_for(self, predicate):
        deadline = time.time() + 1
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return False

    def bridge(self, enabled=False, factory=None, secure_mode_provider=None):
        directory = tempfile.mkdtemp(prefix="ble-tls-gatt-")
        return RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": directory,
            "ble_http_base_url": "http://127.0.0.1:8787",
            "ble_authorization_tls_relay_enabled": enabled,
        }, authorization_runtime=Runtime(), tls_relay_factory=factory,
            secure_mode_policy_provider=secure_mode_provider)

    def test_secure_mode_provider_blocks_legacy_clinical_operations(self):
        bridge = self.bridge(
            secure_mode_provider=lambda: SecureModePolicy(SecureModePolicy.READY))
        for operation in ("event_write", "event_ack", "status", "pump_history",
                          "device_status", "bg_readings"):
            with self.assertRaises(BleProtocolError):
                bridge.require_legacy_ble(operation)
        # Rig metadata and the dedicated encrypted relay remain bootstrap /
        # transport operations rather than legacy clinical paths.
        bridge.require_legacy_ble("rig_info")
        bridge.require_legacy_ble("authorization_ack")
        with self.assertRaises(BleProtocolError):
            bridge.submit_ble_write(json.dumps({
                "schema": "openaps.local.event.v1",
                "event_id": "legacy-placeholder",
            }).encode("utf-8"), "connection-a")

    def test_secure_mode_provider_failure_fails_closed_and_disabled_preserves_legacy(self):
        unavailable = self.bridge(secure_mode_provider=lambda: None)
        with self.assertRaises(BleProtocolError):
            unavailable.require_legacy_ble("status")
        disabled = self.bridge(
            secure_mode_provider=lambda: SecureModePolicy(SecureModePolicy.DISABLED))
        disabled.require_legacy_ble("status")

    def test_default_off_does_not_construct_or_advertise_relay(self):
        factory = RelayFactory()
        bridge = self.bridge(factory=factory)
        with self.assertRaises(BleProtocolError):
            bridge.submit_tls_relay_frame(encode_tls_relay_frame(b"hello"), "connection-a")
        self.assertEqual(factory.instances, [])
        self.assertNotIn("authorization_tls_relay_v1",
                         bridge.rig_info_payload("connection-a")["capabilities"])
        self.assertNotIn("maintenance_deflate_raw_v1",
                         bridge.rig_info_payload("connection-a")["capabilities"])

    def test_single_session_frames_remain_opaque(self):
        factory = RelayFactory()
        bridge = self.bridge(True, factory)
        self.assertIn("maintenance_deflate_raw_v1",
                      bridge.rig_info_payload("connection-a")["capabilities"])
        first = b"\x16\x03\x03\x00\x01a"
        second = b"\x00opaque\xff"
        bridge.submit_tls_relay_frame(encode_tls_relay_frame(first), "connection-a")
        bridge.submit_tls_relay_frame(encode_tls_relay_frame(second), "connection-a")
        self.assertEqual(len(factory.instances), 1)
        self.assertTrue(self.wait_for(lambda: factory.instances[0].sent == [first, second]))
        self.assertEqual(factory.instances[0].sent, [first, second])
        factory.instances[0].incoming.append(second)
        self.assertTrue(self.wait_for(lambda:
            not bridge._tls_relays_by_connection["connection-a"].inbound.empty()))
        self.assertEqual(decode_tls_relay_frame(
            bridge.read_tls_relay_frame("connection-a")), second)

    def test_frame_bounds_and_shape_fail_before_connect(self):
        factory = RelayFactory()
        bridge = self.bridge(True, factory)
        with self.assertRaises(BleProtocolError):
            bridge.submit_tls_relay_frame(b"{}", "connection-a")
        oversized = json.dumps({
            "schema": "openaps.ble.tls-frame.v1",
            "payload": base64.b64encode(b"x" * (MAX_TLS_RELAY_FRAME_BYTES + 1)).decode("ascii"),
        }).encode("utf-8")
        with self.assertRaises(BleProtocolError):
            bridge.submit_tls_relay_frame(oversized, "connection-a")
        self.assertEqual(factory.instances, [])
        encoded = encode_tls_relay_frame(b"x" * MAX_TLS_RELAY_FRAME_BYTES)
        self.assertLessEqual(len(encoded), 184)
        self.assertEqual(decode_tls_relay_frame(encode_tls_relay_frame(b"")), b"")

    def test_unrelated_disconnect_does_not_close_active_session(self):
        factory = RelayFactory()
        bridge = self.bridge(True, factory)
        frame = encode_tls_relay_frame(b"hello")
        bridge.submit_tls_relay_frame(frame, "connection-a")
        self.assertTrue(bridge.handle_device_properties_changed(
            BLUEZ_DEVICE_IFACE, {"Connected": False}, "connection-b"))
        self.assertFalse(factory.instances[0].closed)
        self.assertIn("connection-a", bridge._tls_relays_by_connection)
        bridge.clear_connection_state("connection-a")
        self.assertTrue(factory.instances[0].closed)

    def test_single_relay_cap_preserves_legacy_work_while_pending(self):
        release = threading.Event()

        class SlowRelay(FakeRelay):
            def open(self):
                release.wait(1)
                return super(SlowRelay, self).open()

        factory = RelayFactory()

        def make(origin, timeout):
            relay = SlowRelay(origin, timeout)
            factory.instances.append(relay)
            return relay

        bridge = self.bridge(True, make)
        # A stale or future deployment setting cannot consume both entries in
        # the HTTP owner's two-entry pending-handshake pool through BLE.
        bridge.config["ble_authorization_tls_relay_connections"] = 2
        frame = encode_tls_relay_frame(b"hello")
        bridge.submit_tls_relay_frame(frame, "connection-a")
        with self.assertRaisesRegex(BleProtocolError, "busy"):
            bridge.submit_tls_relay_frame(frame, "connection-b")
        self.assertEqual(len(factory.instances), 1)

        legacy_done = threading.Event()
        bridge.post_event = lambda _event: {"schema": "openaps.local.event_ack.v1"}
        bridge.submit_ble_write_async(json.dumps({
            "schema": "openaps.local.event.v1",
            "event_id": "legacy-placeholder",
        }).encode("utf-8"), "connection-legacy", lambda _ack: legacy_done.set(),
            lambda _error: legacy_done.set())
        self.assertTrue(legacy_done.wait(0.5))
        release.set()
        bridge.clear_connection_state("connection-a")
        bridge.submit_tls_relay_frame(frame, "connection-b")
        self.assertEqual(len(factory.instances), 2)
        bridge.clear_connection_state("connection-b")

    def test_unavailable_relay_fails_closed_without_session(self):
        factory = RelayFactory(fail=True)
        bridge = self.bridge(True, factory)
        try:
            bridge.submit_tls_relay_frame(encode_tls_relay_frame(b"hello"), "connection-a")
        except BleProtocolError:
            pass
        self.assertEqual(len(factory.instances), 1)
        self.assertTrue(self.wait_for(lambda: factory.instances[0].closed))
        with self.assertRaises(BleProtocolError):
            bridge.read_tls_relay_frame("connection-a")
        self.assertEqual(bridge._tls_relays_by_connection, {})

    def test_slow_upgrade_and_empty_read_never_block_gatt_caller(self):
        release = threading.Event()

        class SlowRelay(FakeRelay):
            def open(self):
                release.wait(1)
                return super(SlowRelay, self).open()

        factory = RelayFactory()

        def make(origin, timeout):
            relay = SlowRelay(origin, timeout)
            factory.instances.append(relay)
            return relay

        bridge = self.bridge(True, make)
        started = time.monotonic()
        bridge.submit_tls_relay_frame(encode_tls_relay_frame(b"hello"), "connection-a")
        session = bridge._tls_relays_by_connection["connection-a"]
        self.assertLess(time.monotonic() - started, 0.1)
        started = time.monotonic()
        with self.assertRaises(BleProtocolError):
            bridge.read_tls_relay_frame("connection-a")
        self.assertLess(time.monotonic() - started, 0.1)
        self.assertIs(bridge._tls_relays_by_connection["connection-a"], session)
        legacy_done = threading.Event()
        bridge.post_event = lambda _event: {"schema": "openaps.local.event_ack.v1"}
        bridge.submit_ble_write_async(json.dumps({
            "schema": "openaps.local.event.v1",
            "event_id": "legacy-placeholder",
        }).encode("utf-8"), "connection-legacy", lambda _ack: legacy_done.set(),
            lambda _error: legacy_done.set())
        self.assertTrue(legacy_done.wait(0.5))
        release.set()
        bridge.clear_connection_state("connection-a")
        self.assertTrue(session.stopped.wait(1))
        self.assertNotIn("connection-a", bridge._tls_relays_by_connection)

    def test_outbound_queue_is_bounded_while_upgrade_is_pending(self):
        release = threading.Event()

        class SlowRelay(FakeRelay):
            def open(self):
                release.wait(1)
                return super(SlowRelay, self).open()

        instances = []
        def make(origin, timeout):
            relay = SlowRelay(origin, timeout)
            instances.append(relay)
            return relay

        bridge = self.bridge(True, make)
        frame = encode_tls_relay_frame(b"x")
        bridge.submit_tls_relay_frame(frame, "connection-a")
        session = bridge._tls_relays_by_connection["connection-a"]
        for _index in range(31):
            bridge.submit_tls_relay_frame(frame, "connection-a")
        with self.assertRaises(BleProtocolError):
            bridge.submit_tls_relay_frame(frame, "connection-a")
        release.set()
        bridge.clear_connection_state("connection-a")
        self.assertTrue(session.stopped.wait(1))


if __name__ == "__main__":
    unittest.main()
