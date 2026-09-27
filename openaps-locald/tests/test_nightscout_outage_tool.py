import importlib.machinery
import calendar
import datetime
import json
import os
import socket
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "bin",
                                      "oref0-test-nightscout-outage"))
outage = importlib.machinery.SourceFileLoader("nightscout_outage_tool", SCRIPT).load_module()


class NightscoutOutageToolTests(unittest.TestCase):
    def test_endpoint_reads_host_without_exposing_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "ns.ini"), "w", encoding="utf-8") as handle:
                handle.write('[device "ns"]\nargs = ns http://example.invalid:1234 token=synthetic-secret\n')
            self.assertEqual(outage.nightscout_endpoint(directory), ("example.invalid", 1234))

    def test_special_use_targets_are_refused(self):
        answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 1234))]
        with patch.object(outage.socket, "getaddrinfo", return_value=answer):
            with self.assertRaises(ValueError):
                outage.targets_for("example.invalid", 1234)

    def test_restore_timer_is_armed_before_firewall_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            commands = []
            with patch.object(outage, "STATE", os.path.join(directory, "state.json")), \
                 patch.object(outage, "nightscout_endpoint", return_value=("example.invalid", 1234)), \
                 patch.object(outage, "targets_for", return_value=[(socket.AF_INET, "192.0.2.10")]), \
                 patch.object(outage, "can_connect", side_effect=[True, False]), \
                 patch.object(outage, "chain_exists", return_value=False), \
                 patch.object(outage.shutil, "which", return_value="/sbin/iptables"), \
                 patch.object(outage.os, "geteuid", return_value=0), \
                 patch.object(outage, "run", side_effect=lambda command: commands.append(command)):
                outage.start(directory, 120)
                self.assertEqual(commands[0][0], "systemd-run")
                self.assertEqual(commands[1][:3], ["iptables", "-N", outage.CHAIN])
                self.assertIn("192.0.2.10", commands[2])
                self.assertTrue(os.path.exists(outage.STATE))

    def test_expiry_cleanup_does_not_require_nightscout_config(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(outage, "STATE", os.path.join(directory, "state.json")), \
                 patch.object(outage, "LAST_RESULT", os.path.join(directory, "last.json")), \
                 patch.object(outage, "remove_rules") as remove, \
                 patch.object(outage.subprocess, "run"):
                outage.write_state({"expires_at": 100, "families": [socket.AF_INET],
                                    "unit": "synthetic", "target_count": 1,
                                    "started_at": 99})
                with patch.object(outage.time, "time", return_value=101):
                    outage.status(directory)
                remove.assert_called_once_with([socket.AF_INET])
                self.assertFalse(os.path.exists(outage.STATE))
                self.assertTrue(os.path.exists(outage.LAST_RESULT))

    def test_observe_arms_snapshot_without_firewall_or_nightscout(self):
        with tempfile.TemporaryDirectory() as directory:
            commands = []
            with patch.object(outage, "STATE", os.path.join(directory, "state.json")), \
                 patch.object(outage.os, "geteuid", return_value=0), \
                 patch.object(outage, "nightscout_endpoint", side_effect=AssertionError), \
                 patch.object(outage, "run", side_effect=lambda command: commands.append(command)):
                outage.observe(directory, 120)
                self.assertEqual(outage.read_state()["mode"], "observe")
                self.assertEqual(len(commands), 1)
                self.assertEqual(commands[0][0], "systemd-run")
                self.assertEqual(commands[0][-2:], ["--myopenaps-dir", directory])

    def test_observation_stop_saves_evidence_after_network_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(outage, "STATE", os.path.join(directory, "state.json")), \
                 patch.object(outage, "LAST_RESULT", os.path.join(directory, "last.json")), \
                 patch.object(outage, "remove_rules") as remove, \
                 patch.object(outage.subprocess, "run"), \
                 patch.object(outage, "loop_evidence", return_value={"ordered_loop_candidate": True}), \
                 patch.object(outage, "pump_history_evidence", return_value={"temp_basal_new": True}):
                outage.write_state({"mode": "observe", "started_at": 100,
                                    "expires_at": 200, "families": [],
                                    "unit": "synthetic", "target_count": 0})
                outage.stop(directory)
                remove.assert_called_once_with([])
                self.assertFalse(os.path.exists(outage.STATE))
                with open(outage.LAST_RESULT, encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.assertTrue(saved["evidence_available"])
                self.assertTrue(saved["ordered_loop_candidate"])
                self.assertTrue(saved["temp_basal_new"])

    def test_loop_evidence_requires_new_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            os.makedirs(os.path.join(directory, "monitor"))
            os.makedirs(os.path.join(directory, "enact"))
            glucose = os.path.join(directory, "monitor", "glucose.json")
            suggested = os.path.join(directory, "enact", "suggested.json")
            for path in (glucose, suggested):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("[]")
            os.utime(glucose, (100, 100))
            os.utime(suggested, (102, 102))
            with patch.object(outage, "marker_time", side_effect=lambda path:
                              103 if path == "/tmp/pump_loop_success" else os.stat(path).st_mtime):
                evidence = outage.loop_evidence(directory, 101)
            self.assertFalse(evidence["glucose_new"])
            self.assertTrue(evidence["suggested_new"])
            self.assertTrue(evidence["loop_success_new"])
            self.assertFalse(evidence["ordered_loop_candidate"])

    def test_ordered_loop_candidate_requires_fresh_glucose_first(self):
        def times_for(glucose, suggested, completed):
            return lambda path: (glucose if path.endswith("glucose.json") else
                                 suggested if path.endswith("suggested.json") else completed)

        with patch.object(outage, "marker_time", side_effect=times_for(101, 102, 103)):
            evidence = outage.loop_evidence("/unused", 100)
        self.assertTrue(evidence["ordered_loop_candidate"])
        with patch.object(outage, "marker_time", side_effect=times_for(101, 100, 103)):
            evidence = outage.loop_evidence("/unused", 100)
        self.assertFalse(evidence["ordered_loop_candidate"])

    def test_pump_history_evidence_uses_event_times_without_therapy_values(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = os.path.join(directory, "monitor")
            os.makedirs(monitor)
            history = os.path.join(monitor, "pumphistory-merged.json")
            with open(history, "w", encoding="utf-8") as handle:
                json.dump([
                    {"_type": "PumpSuspend", "dateString": "2026-01-01T00:00:00Z"},
                    {"_type": "PumpResume", "dateString": "2026-01-01T00:05:00Z"},
                    {"_type": "TempBasal", "dateString": "2026-01-01T00:06:00Z"},
                ], handle)
            started_at = calendar.timegm(datetime.datetime(2026, 1, 1, 0, 3).timetuple())
            os.utime(history, (started_at + 240, started_at + 240))
            evidence = outage.pump_history_evidence(directory, started_at)
            self.assertEqual(evidence, {
                "pump_history_available": True,
                "pump_history_updated": True,
                "pump_resume_new": True,
                "temp_basal_new": True,
            })
            evidence = outage.pump_history_evidence(directory, started_at + 600)
            self.assertTrue(evidence["pump_history_available"])
            self.assertFalse(evidence["pump_history_updated"])
            self.assertFalse(evidence["pump_resume_new"])
            self.assertFalse(evidence["temp_basal_new"])

    def test_missing_pump_history_is_reported_as_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = outage.pump_history_evidence(directory, 100)
            self.assertFalse(evidence["pump_history_available"])
            self.assertFalse(evidence["temp_basal_new"])

    def test_new_raw_pump_event_is_not_hidden_by_stale_merged_history(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = os.path.join(directory, "monitor")
            os.makedirs(monitor)
            merged = os.path.join(monitor, "pumphistory-merged.json")
            raw = os.path.join(monitor, "pumphistory.json")
            with open(merged, "w", encoding="utf-8") as handle:
                json.dump([{"_type": "PumpSuspend", "dateString": "2026-01-01T00:00:00Z"}], handle)
            with open(raw, "w", encoding="utf-8") as handle:
                json.dump([{"_type": "TempBasal", "dateString": "2026-01-01T00:06:00Z"}], handle)
            started_at = calendar.timegm(datetime.datetime(2026, 1, 1, 0, 3).timetuple())
            os.utime(merged, (started_at - 60, started_at - 60))
            os.utime(raw, (started_at + 240, started_at + 240))
            evidence = outage.pump_history_evidence(directory, started_at)
            self.assertTrue(evidence["pump_history_updated"])
            self.assertTrue(evidence["temp_basal_new"])

    def test_failed_firewall_install_rolls_back_and_cancels_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "state.json")
            commands = []

            def record_or_fail(command):
                commands.append(command)
                if command[:2] == ["iptables", "-I"]:
                    raise outage.subprocess.CalledProcessError(1, command)

            with patch.object(outage, "STATE", state_path), \
                 patch.object(outage, "nightscout_endpoint", return_value=("example.invalid", 1234)), \
                 patch.object(outage, "targets_for", return_value=[(socket.AF_INET, "192.0.2.10")]), \
                 patch.object(outage, "can_connect", return_value=True), \
                 patch.object(outage, "chain_exists", return_value=False), \
                 patch.object(outage.shutil, "which", return_value="/sbin/iptables"), \
                 patch.object(outage.os, "geteuid", return_value=0), \
                 patch.object(outage, "remove_rules") as remove, \
                 patch.object(outage.subprocess, "run") as systemctl, \
                 patch.object(outage, "run", side_effect=record_or_fail):
                with self.assertRaises(outage.subprocess.CalledProcessError):
                    outage.start(directory, 120)
                remove.assert_called_once_with([socket.AF_INET])
                self.assertFalse(os.path.exists(state_path))
                self.assertEqual(systemctl.call_args[0][0][:2], ["systemctl", "stop"])


if __name__ == "__main__":
    unittest.main()
