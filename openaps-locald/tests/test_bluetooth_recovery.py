import json
import os
import subprocess
import tempfile
import unittest
from openaps_locald import bluetooth_recovery as recovery


class BluetoothRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "attempt.json")
        self.commands = []
        self.links = b"Connections:\n"
        self.running = False
        self.failure = None
        self.exit_status = b"ExecMainStatus=75\n"
        self.now = 1000

    def tearDown(self):
        self.directory.cleanup()

    def run_command(self, command, timeout):
        self.commands.append((command, timeout))
        if command[1] == "is-active" and not self.running:
            raise subprocess.CalledProcessError(3, command)
        if self.failure and command[1] == self.failure:
            raise subprocess.TimeoutExpired(command, timeout)

    def capture(self, command, timeout, stderr=None):
        if command[0] == "systemctl":
            self.assertEqual(command, ["systemctl", "show", recovery.ADVERTISER, "-p", "ExecMainStatus"])
            return self.exit_status
        self.assertEqual(command, ["hcitool", "con"])
        self.assertEqual(timeout, 5)
        return self.links

    def recover(self):
        return recovery.recover_once(self.path, self.run_command, self.capture, lambda: self.now)

    def test_healthy_advertiser_never_resets_controller(self):
        self.running = True
        self.assertEqual(self.recover(), "already_running")
        self.assertEqual(len(self.commands), 1)
        self.assertFalse(os.path.exists(self.path))

    def test_other_startup_failures_do_not_reset_controller(self):
        for status in (b"ExecMainStatus=1\n", b"ExecMainStatus=0\n", b"unknown"):
            self.exit_status = status
            self.assertEqual(self.recover(), "failure_not_controller_enable")
            self.assertFalse(os.path.exists(self.path))

    def test_live_or_unknown_connections_defer_without_reset(self):
        for links in (b"Connections:\n  < [synthetic-link]\n", b"", b"unavailable\n"):
            self.links = links
            self.commands = []
            self.assertEqual(self.recover(), "connections_active_or_unknown")
            self.assertEqual(self.commands[-1][0], ["systemctl", "restart", recovery.RETRY_TIMER])
            self.assertFalse(os.path.exists(self.path))

    def test_failed_advertiser_recovers_only_bluetooth_and_ble(self):
        self.assertEqual(self.recover(), "restart_requested")
        self.assertEqual(self.commands[1:], [
            (["systemctl", "reset-failed", recovery.ADVERTISER], 5),
            (["systemctl", "restart", "bluetooth.service"], 30),
            (["systemctl", "start", recovery.BLE], 30)])
        with open(self.path) as handle:
            self.assertEqual(json.load(handle), {"attempted_at": self.now})

    def test_repeated_failures_back_off_before_resetting_again(self):
        self.recover()
        self.commands = []
        self.now += 119
        self.assertEqual(self.recover(), "cooldown")
        self.assertEqual(len(self.commands), 2)
        self.now += 1
        self.assertEqual(self.recover(), "restart_requested")

    def test_partial_recovery_still_retains_cooldown(self):
        self.failure = "start"
        self.assertEqual(self.recover(), "recovery_deferred")
        self.failure = None
        self.now += 1
        self.assertEqual(self.recover(), "cooldown")

    def test_unavailable_clock_cannot_trigger_controller_reset(self):
        for instant in (float("nan"), float("inf"), -1):
            self.now = instant
            self.assertEqual(self.recover(), "clock_unavailable")
            self.assertFalse(os.path.exists(self.path))

    def test_clock_rollback_retains_recovery_boundary(self):
        self.recover()
        self.now -= 1
        self.assertEqual(self.recover(), "clock_unavailable")

    def test_retry_scheduler_failure_does_not_repeat_or_reset(self):
        self.links = b"unavailable"
        self.failure = "restart"
        self.assertEqual(self.recover(), "connections_active_or_unknown_retry_unavailable")
        self.assertEqual(len(self.commands), 2)
