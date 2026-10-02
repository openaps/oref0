import threading
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from openaps_locald import ble_server
from openaps_locald.ble_protocol import (
    BLE_BACKGROUND_WAKE_CAPABILITY, BLE_BACKGROUND_WAKE_CHAR_UUID,
    BLE_CHARACTERISTIC_UUIDS, BLE_TLS_CHARACTERISTIC_UUIDS, BleProtocolError,
)
from openaps_locald.ble_wake import BackgroundWakeTicker, wake_interval
from openaps_locald.config import default_config
from openaps_locald.secure_mode import SecureModePolicy


class Scheduler(object):
    def __init__(self):
        self.callbacks = {}
        self.removed = []
        self.periods = []

    def add(self, seconds, callback):
        self.periods.append(seconds)
        source = len(self.periods)
        self.callbacks[source] = callback
        return source

    def remove(self, source):
        # Retain the callback so tests can simulate dispatch already queued
        # before GLib source removal.
        self.removed.append(source)


class BackgroundWakeTests(unittest.TestCase):
    def ticker(self, emit=None):
        scheduler = Scheduler()
        values = []
        ticker = BackgroundWakeTicker(60, scheduler.add, scheduler.remove,
                                      emit or values.append)
        return ticker, scheduler, values

    def test_subscription_owns_one_source_and_retired_callbacks_cannot_emit(self):
        ticker, scheduler, values = self.ticker()
        ticker.start()
        ticker.start()
        self.assertEqual(scheduler.periods, [60])
        self.assertEqual(values, [])
        self.assertTrue(scheduler.callbacks[1]())
        self.assertEqual(values, [b"\x01\x01"])
        ticker.stop()
        ticker.stop()
        self.assertEqual(scheduler.removed, [1])
        ticker.start()
        self.assertFalse(scheduler.callbacks[1]())
        self.assertTrue(scheduler.callbacks[2]())
        self.assertEqual(values, [b"\x01\x01", b"\x01\x02"])
        ticker.close()
        ticker.close()
        ticker.start()
        self.assertFalse(scheduler.callbacks[2]())
        self.assertEqual(scheduler.periods, [60, 60])
        self.assertEqual(scheduler.removed, [1, 2])

    def test_ticks_are_bounded_and_counter_wraps(self):
        ticker, scheduler, values = self.ticker()
        ticker.start()
        for _ in range(513):
            self.assertTrue(scheduler.callbacks[1]())
        self.assertEqual(scheduler.periods, [60])
        self.assertTrue(all(len(value) == 2 and value[0] == 1 for value in values))
        self.assertEqual(values[255], b"\x01\x00")
        self.assertEqual(values[512], b"\x01\x01")

    def test_failed_notification_retires_source_without_retry_loop(self):
        def fail(_value):
            raise RuntimeError("synthetic")
        ticker, scheduler, _values = self.ticker(fail)
        ticker.start()
        self.assertFalse(scheduler.callbacks[1]())
        self.assertIsNone(ticker.source)
        ticker.start()
        self.assertFalse(scheduler.callbacks[1]())
        self.assertEqual(scheduler.periods, [60, 60])

    def test_close_waits_for_in_progress_emit_and_blocks_later_emissions(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        values = []
        def emit(value):
            entered.set()
            self.assertTrue(release.wait(2))
            values.append(value)
        ticker, scheduler, _ = self.ticker(emit)
        ticker.start()
        worker = threading.Thread(target=scheduler.callbacks[1])
        worker.start()
        self.assertTrue(entered.wait(2))
        closer = threading.Thread(target=lambda: (ticker.close(), closed.set()))
        closer.start()
        self.assertFalse(closed.wait(0.02))
        release.set()
        worker.join(2)
        closer.join(2)
        self.assertTrue(closed.is_set())
        self.assertFalse(scheduler.callbacks[1]())
        self.assertEqual(len(values), 1)

    def test_interval_is_bounded_and_default_is_disabled(self):
        defaults = default_config("/tmp/rig-placeholder")
        self.assertIs(defaults["ble_background_wake_enabled"], False)
        self.assertEqual(wake_interval(defaults), 60)
        for value, expected in [(0, 30), (29, 30), (30, 30), (301, 300),
                                (300, 300), ("90", 90), (None, 60),
                                (True, 60), ("invalid", 60), (float("inf"), 60)]:
            self.assertEqual(wake_interval({"ble_background_wake_interval_seconds": value}), expected)

    def test_registration_capability_and_notify_contract_without_clinical_io(self):
        runtime = SimpleNamespace(identity=None, client=None, mode="legacy")
        scheduler = Scheduler()
        def characteristic_init(instance, bus, bus_name, index, uuid, service, flags):
            instance.uuid, instance.flags = uuid, flags
            instance.value, instance.notifying = b"", False
        with ExitStack() as stack:
            stack.enter_context(patch.object(ble_server.Characteristic, "__init__", characteristic_init))
            stack.enter_context(patch.object(ble_server, "GLib", SimpleNamespace(
                timeout_add_seconds=scheduler.add, source_remove=scheduler.remove)))
            stack.enter_context(patch.object(ble_server.dbus.service, "BusName", create=True))
            stack.enter_context(patch.object(ble_server, "AuthorizationRuntime", return_value=runtime))
            for name in ("Service", "Application", "Advertisement", "LegacyBtMgmtAdvertisement"):
                stack.enter_context(patch.object(ble_server, name))
            io = [stack.enter_context(patch.object(ble_server, name, side_effect=AssertionError("unexpected IO")))
                  for name in ("urlopen", "read_bg_readings_payload", "read_pumphistory_payload",
                               "read_device_status_payload")]
            for enabled in (None, False, "true", True):
                config = {"ble_background_wake_enabled": enabled}
                app = ble_server.LocalBleApplication(None, config,
                    secure_mode_policy_provider=lambda: SecureModePolicy(SecureModePolicy.READY))
                info = app.bridge.rig_info_payload("connection-placeholder")
                self.assertEqual(BLE_BACKGROUND_WAKE_CAPABILITY in info["capabilities"], enabled is True)
                self.assertEqual(app.background_wake is not None, enabled is True)
                if enabled is not True:
                    continue
                wake = app.background_wake
                self.assertEqual(wake.uuid, BLE_BACKGROUND_WAKE_CHAR_UUID)
                self.assertEqual(wake.flags, ["notify"])
                self.assertNotIn(wake.uuid, BLE_CHARACTERISTIC_UUIDS + BLE_TLS_CHARACTERISTIC_UUIDS)
                with patch.object(wake, "PropertiesChanged") as signal, patch.object(
                        ble_server, "_bytes_to_dbus_array", side_effect=lambda value: value):
                    wake.StartNotify()
                    self.assertTrue(scheduler.callbacks[1]())
                    self.assertEqual(signal.call_args[0][1], {"Value": b"\x01\x01"})
                    wake.StopNotify()
                    self.assertFalse(scheduler.callbacks[1]())
                    wake.StartNotify()
                    wake.close()
                    self.assertFalse(scheduler.callbacks[2]())
                    wake.StartNotify()
                    self.assertFalse(wake.notifying)
                self.assertEqual(app.bridge._tls_relays_by_connection, {})
                for operation in ("status", "bg_readings", "event_write"):
                    with self.assertRaises(BleProtocolError):
                        app.bridge.require_legacy_ble(operation)
            self.assertTrue(all(not call.called for call in io))
