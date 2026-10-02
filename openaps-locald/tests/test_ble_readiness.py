import unittest

from openaps_locald.ble_readiness import readiness_failure, wait_until_ready


class BLEReadinessTests(unittest.TestCase):
    def health(self, pid=12345, registered=True, characteristic=True):
        return {"pid": pid, "gatt_registered": registered,
                "characteristics": ["wake-placeholder"] if characteristic else []}

    def wait(self, read, timeout=90):
        clock = [0]
        def sleep(seconds):
            clock[0] += seconds
        wait_until_ready(lambda: read(clock[0]), 12345, "wake-placeholder",
                         timeout, monotonic=lambda: clock[0], sleep=sleep)
        return clock[0]

    def test_delayed_registration_waits_for_new_process(self):
        def read(at):
            if at < 5:
                return self.health(pid=12344)
            return self.health(registered=at >= 31)
        self.assertEqual(self.wait(read), 31)

    def test_stale_registered_health_cannot_pass(self):
        with self.assertRaisesRegex(RuntimeError, "health_process_mismatch"):
            self.wait(lambda _: self.health(pid=12344), timeout=3)

    def test_missing_characteristic_reports_exact_failed_gate(self):
        with self.assertRaisesRegex(RuntimeError, "required_characteristic_missing"):
            self.wait(lambda _: self.health(characteristic=False), timeout=3)

    def test_malformed_health_recovers_without_accepting_it(self):
        self.assertEqual(self.wait(lambda at: [] if at < 2 else self.health()), 2)

    def test_unregistered_gatt_and_invalid_bounds_fail_closed(self):
        self.assertEqual(readiness_failure(self.health(registered=False), 12345,
                                           "wake-placeholder"), "gatt_not_registered")
        with self.assertRaises(ValueError):
            wait_until_ready(lambda: self.health(), 0, "wake-placeholder")
        with self.assertRaises(ValueError):
            self.wait(lambda _: self.health(), timeout=181)
