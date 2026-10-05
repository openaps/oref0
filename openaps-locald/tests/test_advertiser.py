import unittest
from unittest.mock import patch

from openaps_locald import advertiser


def command_complete(opcode=0x200a, status=0, extra=()):
    payload = [1, opcode & 0xff, opcode >> 8, status] + list(extra)
    return ("< HCI Command: ogf 0x08, ocf 0x000a, plen 1\n"
            "  01\n> HCI Event: 0x0e plen %d\n  %s\n" %
            (len(payload), " ".join("%02X" % byte for byte in payload))).encode("ascii")


class AdvertiserCommandStatusTests(unittest.TestCase):
    def make_advertiser(self):
        return advertiser.RawHciAdvertiser({
            "ble_name": "rig-demo", "advertise_manage_visibility": False,
            "ble_service_uuid": "12345678-1234-1234-1234-123456789abc",
        })

    def test_enable_does_not_claim_controller_rejection_as_success(self):
        instance = self.make_advertiser()
        instance.last_enable_at = "previous-success"
        with patch.object(advertiser.subprocess, "check_output", return_value=command_complete(status=0x0c)):
            self.assertFalse(instance.enable_once())
        self.assertEqual(instance.last_enable_at, "previous-success")
        self.assertIn("status=0x0c", instance.last_error)

    def test_start_cannot_mark_running_after_controller_rejection(self):
        instance = self.make_advertiser()
        def response(command, **_kwargs):
            opcode = (int(command[4], 16) << 10) | int(command[5], 16)
            return command_complete(opcode, status=0x12 if opcode == 0x2006 else 0)
        with patch.object(advertiser.subprocess, "check_output", side_effect=response):
            with self.assertRaisesRegex(RuntimeError, "status=0x12"):
                instance.start()
        self.assertFalse(instance.health_payload("test")["running"])
        self.assertIsNone(instance.last_enable_at)

    def test_successful_enable_preserves_existing_command_and_records_acceptance(self):
        instance = self.make_advertiser()
        with patch.object(advertiser.subprocess, "check_output", return_value=command_complete()) as run:
            with patch.object(advertiser, "_utc_now", return_value="accepted-now"):
                self.assertTrue(instance.enable_once())
        run.assert_called_once_with(
            ["hcitool", "-i", "hci0", "cmd", "0x08", "0x000a", "0x01"],
            stderr=advertiser.subprocess.STDOUT)
        self.assertEqual(instance.last_enable_at, "accepted-now")
        self.assertIsNone(instance.last_error)

    def test_successful_start_disables_once_before_setup_and_enable(self):
        instance = self.make_advertiser()
        calls = []
        def response(command, **_kwargs):
            calls.append(command)
            opcode = (int(command[4], 16) << 10) | int(command[5], 16)
            return command_complete(opcode)
        with patch.object(advertiser.subprocess, "check_output", side_effect=response):
            instance.start()
        self.assertEqual(calls, [instance._hcitool_command(8, 10, [0])] + instance.command_sequence())
        self.assertTrue(instance._running)
        self.assertEqual(sum(command[5:] == ["0x000a", "0x00"] for command in calls), 1)

    def test_mismatched_opcode_never_records_success(self):
        instance = self.make_advertiser()
        with patch.object(advertiser.subprocess, "check_output", return_value=command_complete(0x2009)):
            self.assertFalse(instance.enable_once())
        self.assertIsNone(instance.last_enable_at)
        self.assertIn("opcode mismatch", instance.last_error)

    def test_malformed_or_unrelated_event_cannot_confirm_enable(self):
        invalid = [
            b"", b"\xff", b"< HCI Command: ogf 0x08, ocf 0x000a, plen 1\n  00\n",
            b"> HCI Event: 0x0e plen 4\n  01 0A 20\n",
            b"> HCI Event: 0x0e plen 3\n  01 0A 20 00\n",
            b"> HCI Event: 0x0e plen 4\n  01 0A 20 GG\n",
            b"> HCI Event: 0x0f plen 4\n  00 01 0A 20\n",
            command_complete() + b"> HCI Event: 0x0e plen 4\n  01 0A 20 00\n",
            b"> HCI Event: 0x0e plen 256\n  01 0A 20 00" + b" 00" * 252 + b"\n",
            command_complete() + b"x" * 4096,
        ]
        for output in invalid:
            instance = self.make_advertiser()
            with patch.object(advertiser.subprocess, "check_output", return_value=output):
                self.assertFalse(instance.enable_once(), repr(output[:80]))
            self.assertIsNone(instance.last_enable_at)
            self.assertEqual(instance.last_error, "invalid HCI command response")

    def test_parser_accepts_native_shape_with_synthetic_extra_return_parameters(self):
        # Read-local-version replies have this shape; fixture bytes are synthetic.
        output = command_complete(0x1001, extra=[0] * 8)
        advertiser._validate_hci_command_response(output, 0x1001)

    def test_subprocess_failure_keeps_previous_success_timestamp(self):
        instance = self.make_advertiser()
        instance.last_enable_at = "previous-success"
        with patch.object(advertiser.subprocess, "check_output", side_effect=OSError("synthetic command failure")):
            self.assertFalse(instance.enable_once())
        self.assertEqual(instance.last_enable_at, "previous-success")
        self.assertIsNotNone(instance.last_error_at)


class StatefulController(object):
    """Model a controller that rejects redundant state requests."""
    def __init__(self, enabled, fail_opcode=None, fail_final_enable=False):
        self.enabled = enabled
        self.fail_opcode = fail_opcode
        self.fail_final_enable = fail_final_enable
        self.calls = []

    def __call__(self, command, **_kwargs):
        opcode = (int(command[4], 16) << 10) | int(command[5], 16)
        status = 0
        if opcode == self.fail_opcode:
            status = 0x12
        elif opcode == 0x200a:
            desired = bool(int(command[6], 16))
            if desired == self.enabled or (desired and self.fail_final_enable):
                status = 0x0c
            else:
                self.enabled = desired
        elif self.enabled:
            status = 0x0c
        self.calls.append((opcode, list(command[6:]), status))
        return command_complete(opcode, status)


class AdvertiserStatefulStartupTests(unittest.TestCase):
    make_advertiser = AdvertiserCommandStatusTests.make_advertiser
    def test_initially_enabled_controller_starts_with_one_disable(self):
        instance = self.make_advertiser()
        controller = StatefulController(True)
        with patch.object(advertiser.subprocess, "check_output", side_effect=controller):
            instance.start()
        self.assertTrue(controller.enabled)
        self.assertTrue(instance._running)
        self.assertIsNotNone(instance.last_enable_at)
        self.assertEqual([c[0] for c in controller.calls], [0x200a, 0x2006, 0x2008, 0x2009, 0x200a])
        self.assertTrue(all(c[2] == 0 for c in controller.calls))

    def test_initially_disabled_controller_retains_best_effort_stop_then_validates_setup(self):
        instance = self.make_advertiser()
        controller = StatefulController(False)
        with patch.object(advertiser.subprocess, "check_output", side_effect=controller):
            instance.start()
        self.assertEqual(controller.calls[0][2], 0x0c)
        self.assertTrue(all(c[2] == 0 for c in controller.calls[1:]))
        self.assertTrue(controller.enabled)
        self.assertTrue(instance._running)

    def test_each_setup_failure_stays_fatal_and_clears_running(self):
        for opcode in (0x2006, 0x2008, 0x2009):
            instance = self.make_advertiser()
            instance._running = True
            controller = StatefulController(True, fail_opcode=opcode)
            with patch.object(advertiser.subprocess, "check_output", side_effect=controller):
                with self.assertRaisesRegex(RuntimeError, "status=0x12"):
                    instance.start()
            self.assertFalse(instance._running)
            self.assertFalse(controller.enabled)
            self.assertIsNone(instance.last_enable_at)
            self.assertFalse(any(c[0] == 0x200a and c[1] == ["0x01"] for c in controller.calls))

    def test_failed_initial_disable_cannot_bypass_setup_validation(self):
        instance = self.make_advertiser()
        controller = StatefulController(True, fail_opcode=0x200a)
        with patch.object(advertiser.subprocess, "check_output", side_effect=controller):
            with self.assertRaisesRegex(RuntimeError, "status=0x0c"):
                instance.start()
        self.assertFalse(instance._running)
        self.assertTrue(controller.enabled)
        self.assertIsNone(instance.last_enable_at)
        self.assertFalse(any(c[0] == 0x200a and c[1] == ["0x01"] for c in controller.calls))

    def test_final_enable_failure_remains_fatal(self):
        instance = self.make_advertiser()
        controller = StatefulController(False, fail_final_enable=True)
        with patch.object(advertiser.subprocess, "check_output", side_effect=controller):
            with self.assertRaisesRegex(RuntimeError, "status=0x0c"):
                instance.start()
        self.assertFalse(instance._running)
        self.assertFalse(controller.enabled)
        self.assertIsNone(instance.last_enable_at)

    def test_periodic_rejection_does_not_invent_acceptance_or_change_controller_state(self):
        instance = self.make_advertiser()
        controller = StatefulController(True)
        with patch.object(advertiser.subprocess, "check_output", side_effect=controller):
            with patch.object(advertiser, "_utc_now", return_value="startup-accepted"):
                instance.start()
            with patch.object(advertiser, "_utc_now", return_value="repeat-rejected"):
                self.assertFalse(instance.enable_once())
        health = instance.health_payload("test")
        self.assertEqual(health["last_enable_at"], "startup-accepted")
        self.assertEqual(health["last_error_at"], "repeat-rejected")
        self.assertIn("status=0x0c", health["last_error"])
        self.assertTrue(controller.enabled)
        self.assertTrue(health["running"])  # Lifecycle, not an on-air assertion.
        self.assertNotIn("advertising_enabled", health)
        self.assertEqual([c[0] for c in controller.calls].count(0x200a), 3)


if __name__ == "__main__":
    unittest.main()
