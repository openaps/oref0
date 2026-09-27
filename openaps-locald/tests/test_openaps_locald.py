from __future__ import print_function

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
try:
    from http.client import HTTPConnection
    from http.server import HTTPServer
except ImportError:
    from httplib import HTTPConnection
    from BaseHTTPServer import HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from openaps_locald.db import EventDB
from openaps_locald import collector_control
from openaps_locald.bg_history import bg_record_from_event
from openaps_locald.ble_protocol import BLE_CHARACTERISTIC_UUIDS, BLE_SERVICE_UUID
from openaps_locald.config import (
    _ios_patient_id_from_nightscout,
    _patient_id_from_nightscout,
    accepted_patient_ids,
    load_config,
)
from openaps_locald.device_status import read_device_status_payload
from openaps_locald.http_api import _authorization_diagnostics, make_handler
from openaps_locald.install_config import build_install_config
from openaps_locald.materialize import materialize_event, materialize_event_result, read_materialization_state
from openaps_locald.models import ValidationError, validate_event
from openaps_locald.pump_history import read_pumphistory_payload


def temp_event(event_id="evt_1", patient_id="patient_1"):
    return {
        "schema": "openaps.local.event.v1",
        "event_id": event_id,
        "patient_id": patient_id,
        "created_at": "2026-04-28T00:00:00Z",
        "effective_at": "2026-04-28T00:00:00Z",
        "created_by_phone_id": "phone_1",
        "source": "ios",
        "event_type": "temp_target",
        "payload": {
            "target_bottom_mgdl": 110,
            "target_top_mgdl": 110,
            "duration_minutes": 30,
            "reason": None,
            "notes": None,
        },
        "supersedes_event_id": None,
        "signature": None,
    }


def collector_event(desired_state="running", event_id="collector_1"):
    event = temp_event(event_id=event_id)
    event["event_type"] = "cgm_collector_control"
    event["payload"] = {
        "collector": "xdripjs",
        "desired_state": desired_state,
        "transmitter_id": "ABC123",
        "alternate_bluetooth_channel": False,
        "election_id": "election-1",
    }
    return event


def cancel_event(event_id="evt_cancel_1", patient_id="patient_1"):
    event = temp_event(event_id=event_id, patient_id=patient_id)
    event["event_type"] = "cancel_temp_target"
    event["payload"] = {"reason": "user_cancelled"}
    return event


def set_cgm_config_event(event_id="cgm_config_1"):
    event = temp_event(event_id=event_id)
    event["event_type"] = "set_cgm_config"
    event["payload"] = {
        "collector": "xdripjs",
        "transmitter_id": "ABC123",
        "sensor_code": "1234",
        "alternate_bluetooth_channel": True,
        "apply_policy": "all_rigs",
    }
    return event


def bg_event(event_id="bg_1"):
    event = temp_event(event_id=event_id)
    event["event_type"] = "bg_reading"
    event["payload"] = {
        "reading_id": "reading_1",
        "transmitter_id": "ABC123",
        "sensor_id": None,
        "sensor_start_date": None,
        "timestamp": "2026-04-28T00:00:00Z",
        "received_at": "2026-04-28T00:00:01Z",
        "sgv": 123,
        "direction": "Flat",
        "trend_rate_mgdl_minute": 0.5,
        "source": "xdripjs",
        "source_device_id": "rig-demo-1",
        "collector_channel": "xdripjs",
    }
    return event


class LocaldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_validate_temp_target(self):
        event = temp_event()
        validated = validate_event(event)
        self.assertEqual(validated["event_id"], "evt_1")
        self.assertEqual(validated["event_type"], "temp_target")

    def test_patient_identity_accepts_ios_alias_without_changing_deployed_primary(self):
        host = "https://diyps.example.invalid/api/v1?token=placeholder"
        first = _ios_patient_id_from_nightscout(host)
        second = _ios_patient_id_from_nightscout("http://DIYPS.example.invalid/")
        different_port = _ios_patient_id_from_nightscout("https://diyps.example.invalid:8443")
        self.assertEqual(first, second)
        self.assertEqual(first, "ns_896ae7bc1727c74b")
        self.assertNotEqual(first, different_port)
        self.assertEqual(_patient_id_from_nightscout(None), "local-default")
        primary = _patient_id_from_nightscout(host)
        self.assertNotEqual(primary, first)
        self.assertEqual(accepted_patient_ids({
            "patient_id": primary,
            "nightscout_host": host,
        }), set([primary, first]))

    def test_explicit_patient_identity_does_not_accept_derived_aliases(self):
        self.assertEqual(accepted_patient_ids({
            "patient_id": "patient-explicit",
            "nightscout_host": "https://diyps.example.invalid",
        }), set(["patient-explicit"]))

    def test_ble_uuid_contract_includes_ios_bg_characteristic(self):
        self.assertEqual(BLE_SERVICE_UUID, "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0001")
        self.assertEqual(BLE_CHARACTERISTIC_UUIDS, [
            "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0002",
            "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0003",
            "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0004",
            "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0005",
            "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0006",
            "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0007",
            "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0008",
        ])

    def test_validate_rejects_bad_target(self):
        event = temp_event()
        event["payload"]["target_bottom_mgdl"] = 40
        with self.assertRaises(ValidationError):
            validate_event(event)

    def test_validate_collector_control_payload(self):
        validated = validate_event(collector_event())
        self.assertEqual(validated["event_type"], "cgm_collector_control")
        for key, value in (("collector", "other"), ("desired_state", "exec"), ("transmitter_id", "bad"), ("election_id", "")):
            event = collector_event()
            event["payload"][key] = value
            with self.assertRaises(ValidationError):
                validate_event(event)
        event = collector_event()
        event["payload"]["alternate_bluetooth_channel"] = 1
        with self.assertRaises(ValidationError):
            validate_event(event)

    def test_validate_and_materialize_ios_set_cgm_config_payload(self):
        event = set_cgm_config_event()
        validated = validate_event(event)
        self.assertEqual(validated["event_type"], "set_cgm_config")
        config = self._collector_config()
        result = materialize_event(event, config)
        self.assertEqual(result, "materialized_into_xdripjs_config")
        with open(config["xdripjs_config_path"], "r") as f:
            self.assertEqual(json.load(f), {
                "alternate_bluetooth_channel": True,
                "existing": "preserved",
                "transmitter_id": "ABC123",
            })

    def test_validate_set_cgm_config_preserves_legacy_payload(self):
        event = set_cgm_config_event()
        event["payload"] = {"transmitter_id": "XYZ789"}
        validated = validate_event(event)
        self.assertEqual(validated["event_type"], "set_cgm_config")

    def test_validate_set_cgm_config_rejects_unknown_fields(self):
        event = set_cgm_config_event()
        event["payload"]["command"] = "arbitrary"
        with self.assertRaises(ValidationError):
            validate_event(event)

    def test_ios_bg_trend_rate_key_is_preserved(self):
        event = bg_event()
        validate_event(event)
        record = bg_record_from_event(event)
        self.assertEqual(record["trend_rate_mgdl_minute"], 0.5)
        self.assertEqual(record["trend_rate_mgdl_min"], 0.5)

    def _collector_config(self):
        config_path = os.path.join(self.tmp, "xdripjs.json")
        with open(config_path, "w") as f:
            json.dump({"existing": "preserved"}, f)
        return {
            "myopenaps_dir": self.tmp,
            "xdripjs_config_path": config_path,
        }

    def _read_bytes(self, path):
        with open(path, "rb") as f:
            return f.read()

    def test_collector_control_is_idempotent_and_allowlisted(self):
        config = self._collector_config()
        started = []
        cron_lines = []

        def pids():
            return [42] if started else []

        def start():
            started.append(True)
            return mock.Mock()

        def read_crontab():
            return list(cron_lines)

        def install_crontab(lines):
            cron_lines[:] = lines

        with mock.patch.object(collector_control, "_logger_pids", side_effect=pids), mock.patch.object(collector_control, "_start_logger", side_effect=start) as start_mock, mock.patch.object(collector_control, "_read_crontab", side_effect=read_crontab), mock.patch.object(collector_control, "_install_crontab", side_effect=install_crontab):
            first = materialize_event_result(collector_event(), config)
            second = materialize_event_result(collector_event(event_id="collector_2"), config)
        self.assertEqual(first["actual_state"], "running")
        self.assertEqual(first["process_count"], 1)
        self.assertEqual(second["cron_enabled"], True)
        self.assertEqual(start_mock.call_count, 1)
        with open(config["xdripjs_config_path"], "r") as f:
            self.assertEqual(json.load(f), {
                "alternate_bluetooth_channel": False,
                "existing": "preserved",
                "transmitter_id": "ABC123",
            })
        self.assertEqual(cron_lines, [collector_control.MANAGED_CRON_LINE])

    def test_collector_status_does_not_mutate_or_execute(self):
        config = self._collector_config()
        cron_lines = ["# unrelated", collector_control.MANAGED_CRON_LINE]
        before_config = self._read_bytes(config["xdripjs_config_path"])
        with mock.patch.object(collector_control, "_start_logger") as start_mock, mock.patch.object(collector_control, "_stop_loggers") as stop_mock, mock.patch.object(collector_control, "_logger_pids", return_value=[7]), mock.patch.object(collector_control, "_read_crontab", return_value=list(cron_lines)), mock.patch.object(collector_control, "_install_crontab") as install_mock:
            details = materialize_event_result(collector_event(desired_state="status"), config)
        self.assertEqual(details["desired_state"], "status")
        self.assertEqual(details["actual_state"], "running")
        self.assertEqual(details["cron_enabled"], True)
        self.assertEqual(details["collector_health"], "no_direct_reading")
        self.assertIsNone(details["last_direct_bg_millis"])
        self.assertEqual(self._read_bytes(config["xdripjs_config_path"]), before_config)
        self.assertEqual(cron_lines, ["# unrelated", collector_control.MANAGED_CRON_LINE])
        start_mock.assert_not_called()
        stop_mock.assert_not_called()
        install_mock.assert_not_called()

    def test_collector_status_distinguishes_process_from_direct_reading(self):
        config = self._collector_config()
        source = os.path.join(self.tmp, "direct-entry.json")
        config["xdripjs_source_path"] = source
        now_millis = 1800000000000
        with open(source, "w") as handle:
            json.dump({"date": now_millis, "sgv": 110}, handle)
        with mock.patch.object(collector_control, "_logger_pids", return_value=[7]), mock.patch.object(collector_control, "_read_crontab", return_value=[]), mock.patch.object(collector_control.time, "time", return_value=now_millis / 1000.0 + 120):
            fresh = collector_control.read_collector_status(config)
        self.assertEqual(fresh["collector_health"], "fresh_direct_reading")
        self.assertEqual(fresh["last_direct_bg_millis"], now_millis)
        self.assertEqual(fresh["direct_bg_age_seconds"], 120)
        with mock.patch.object(collector_control, "_logger_pids", return_value=[7]), mock.patch.object(collector_control, "_read_crontab", return_value=[]), mock.patch.object(collector_control.time, "time", return_value=now_millis / 1000.0 + 1200):
            stale = collector_control.read_collector_status(config)
        self.assertEqual(stale["collector_health"], "stale_direct_reading")

    def test_collector_stop_only_targets_exact_logger(self):
        config = self._collector_config()
        cron_lines = ["unrelated command /usr/local/bin/Logger-extra", collector_control.MANAGED_CRON_LINE]
        pids = [101]
        installed = []

        def read_crontab():
            return list(cron_lines)

        def install_crontab(lines):
            cron_lines[:] = lines
            installed.append(lines)

        def kill(pid, sig):
            pids.remove(pid)

        with mock.patch.object(collector_control, "_logger_pids", side_effect=lambda: list(pids)), mock.patch.object(collector_control.os, "kill", side_effect=kill) as kill_mock, mock.patch.object(collector_control, "_read_crontab", side_effect=read_crontab), mock.patch.object(collector_control, "_install_crontab", side_effect=install_crontab):
            first = materialize_event_result(collector_event(desired_state="stopped"), config)
            second = materialize_event_result(collector_event(desired_state="stopped", event_id="collector_2"), config)
        kill_mock.assert_called_once_with(101, collector_control.signal.SIGTERM)
        self.assertEqual(first["actual_state"], "stopped")
        self.assertEqual(second["actual_state"], "stopped")
        self.assertEqual(installed, [[
            "unrelated command /usr/local/bin/Logger-extra",
            collector_control.COMMENTED_MANAGED_CRON_LINE,
        ]])

    def test_crontab_install_uses_fixed_command_and_temp_input(self):
        captured = {}

        def check_call(args):
            captured["args"] = args
            with open(args[1], "r") as f:
                captured["content"] = f.read()

        with mock.patch.object(collector_control.subprocess, "check_call", side_effect=check_call):
            collector_control._install_crontab([collector_control.MANAGED_CRON_LINE])
        self.assertEqual(captured["args"][0:1], ["crontab"])
        self.assertEqual(captured["content"], collector_control.MANAGED_CRON_LINE + "\n")

    def test_process_probe_matches_only_allowlisted_logger_shapes(self):
        argv = {
            1: ["/bin/bash", collector_control.LOGGER_PATH],
            2: ["/bin/bash", collector_control.LOGGER_PATH + "-probe"],
            3: ["node", "/root/src/Logger/xdrip-js/bin/xdrip.js"],
            4: ["node", "/tmp/unrelated.js"],
        }
        with mock.patch.object(collector_control.os, "listdir", return_value=["1", "2", "3", "4", "self"]), mock.patch.object(collector_control, "_read_process_state", return_value="S"), mock.patch.object(collector_control, "_read_process_argv", side_effect=lambda pid: argv[pid]):
            self.assertEqual(collector_control._logger_pids(), [1, 3])

    def test_start_logger_uses_deployed_workdir_log_and_detached_session(self):
        popen = mock.Mock(return_value=mock.Mock())
        with mock.patch.object(collector_control.os.path, "exists", return_value=True), mock.patch.object(collector_control, "open", mock.mock_open()), mock.patch.object(collector_control.subprocess, "Popen", popen):
            collector_control._start_logger()
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [collector_control.LOGGER_PATH])
        self.assertEqual(kwargs["cwd"], collector_control.LOGGER_WORKDIR)
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
        self.assertEqual(kwargs["start_new_session"], True)

    def test_config_backup_mode_and_status_report_actual_config(self):
        config = self._collector_config()
        path = config["xdripjs_config_path"]
        os.chmod(path, 0o640)
        payload = collector_event()["payload"]
        with mock.patch.object(collector_control, "_logger_pids", return_value=[]), mock.patch.object(collector_control, "_read_crontab", return_value=[]):
            collector_control._configure(config, payload)
            details = collector_control.read_collector_status(config, dict(payload, transmitter_id="BAD999"))
        self.assertTrue(os.path.exists(path + ".pre-phone-election"))
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)
        self.assertEqual(details["transmitter_id"], "ABC123")
        self.assertEqual(details["alternate_bluetooth_channel"], False)

    def test_config_reuses_ns_ini_token_in_memory_without_copying_it_to_json(self):
        with open(os.path.join(self.tmp, "ns.ini"), "w") as handle:
            handle.write('[device "ns"]\n')
            handle.write('args = ns https://diyps.example.invalid token=subject-placeholder-secret-placeholder\n')
        with open(os.path.join(self.tmp, "preferences.json"), "w") as handle:
            json.dump({"nightscout_host": "https://stale.example.invalid"}, handle)
        config = load_config(myopenaps_dir=self.tmp)
        self.assertEqual(config["nightscout_host"], "https://diyps.example.invalid")
        self.assertEqual(config["nightscout_access_token"], "subject-placeholder-secret-placeholder")
        self.assertEqual(config["authorization_mode"], "shadow")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "openaps-locald.json")))

    def test_config_reuses_bare_ns_ini_token_and_ignores_null_install_placeholders(self):
        with open(os.path.join(self.tmp, "ns.ini"), "w") as handle:
            handle.write('[device "ns"]\n')
            handle.write('args = ns https://diyps.example.invalid subject_placeholder-0123456789abcdef\n')
        with open(os.path.join(self.tmp, "openaps-locald.json"), "w") as handle:
            json.dump({
                "nightscout_host": None,
                "nightscout_access_token": None,
            }, handle)
        config = load_config(myopenaps_dir=self.tmp)
        self.assertEqual(config["nightscout_host"], "https://diyps.example.invalid")
        self.assertEqual(config["nightscout_access_token"], "subject_placeholder-0123456789abcdef")
        self.assertEqual(config["nightscout_credential_kind"], "access_token")

    def test_config_does_not_treat_legacy_api_secret_as_access_token(self):
        with open(os.path.join(self.tmp, "ns.ini"), "w") as handle:
            handle.write('[device "ns"]\n')
            handle.write('args = ns https://diyps.example.invalid 0123456789abcdef0123456789abcdef01234567\n')
        config = load_config(myopenaps_dir=self.tmp)
        self.assertEqual(config["nightscout_host"], "https://diyps.example.invalid")
        self.assertIsNone(config["nightscout_access_token"])
        self.assertEqual(config["nightscout_api_secret"], "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(config["nightscout_credential_kind"], "legacy_api_secret")

    def test_install_config_promotes_null_authorization_defaults_to_shadow(self):
        config = build_install_config(
            {
                "authorization_mode": None,
                "authorization_identity_dir": None,
                "authorization_state_path": None,
                "authorization_openssl_path": None,
            },
            self.tmp,
            "0.0.0.0",
            8787,
        )
        authorization_dir = os.path.join(self.tmp, ".openaps-locald-authorization")
        self.assertEqual(config["authorization_mode"], "shadow")
        self.assertEqual(config["authorization_identity_dir"], authorization_dir)
        self.assertEqual(
            config["authorization_state_path"],
            os.path.join(authorization_dir, "shadow-state.json"),
        )
        self.assertEqual(
            config["authorization_admission_dir"],
            os.path.join(authorization_dir, "admission"),
        )
        self.assertEqual(config["authorization_secure_mode_dir"],
                         os.path.join(authorization_dir, "secure-mode"))
        self.assertEqual(config["authorization_openssl_path"], "/usr/bin/openssl")

    def test_installer_provisions_private_distinct_committed_admission_directory(self):
        installer = os.path.join(os.path.dirname(ROOT), "bin", "openaps-locald-install.sh")
        with open(installer) as handle:
            source = handle.read()
        self.assertIn('"settings-epoch", "key-epoch", "candidates", "committed", "policy-anchor"', source)
        self.assertIn('config["authorization_secure_mode_dir"]', source)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertIn("os.fchmod(descriptor, 0o700)", source)

    def test_install_config_removes_null_nightscout_placeholders(self):
        config = build_install_config(
            {"nightscout_host": None, "nightscout_access_token": None},
            self.tmp,
            "0.0.0.0",
            8787,
        )
        self.assertNotIn("nightscout_host", config)
        self.assertNotIn("nightscout_access_token", config)

    def test_install_config_never_persists_nightscout_authorization_credentials(self):
        config = build_install_config(
            {
                "nightscout_host": "https://diyps.example.invalid",
                "nightscout_access_token": "subject_placeholder-0123456789abcdef",
                "nightscout_api_secret": "0" * 40,
                "nightscout_credential_kind": "legacy_api_secret",
            },
            self.tmp,
            "0.0.0.0",
            8787,
        )
        self.assertEqual(config["nightscout_host"], "https://diyps.example.invalid")
        self.assertNotIn("nightscout_access_token", config)
        self.assertNotIn("nightscout_api_secret", config)
        self.assertNotIn("nightscout_credential_kind", config)

    def test_authorization_diagnostics_exposes_only_error_category(self):
        class Identity(object):
            credential_id = "a" * 64

        class Runtime(object):
            mode = "shadow"
            identity = Identity()
            credential_id = Identity.credential_id
            last_state = {
                "classification": "error",
                "last_attempt_error": "permission",
            }

        diagnostics = _authorization_diagnostics(Runtime())
        self.assertEqual(diagnostics["mode"], "shadow")
        self.assertEqual(diagnostics["state"], "error")
        self.assertEqual(diagnostics["error_category"], "permission")
        self.assertEqual(diagnostics["credential_id_hint"], "aaaaaaaa...aaaaaaaa")
        self.assertNotIn("credential_id", diagnostics)

    def test_installed_wrappers_prefer_installed_package_over_checkout(self):
        wrappers = [
            "openaps-locald",
            "openaps-locald-advertise",
            "openaps-locald-authorization-smoke",
            "openaps-locald-ble",
            "openaps-locald-merge-carbs",
            "openaps-locald-replay-cgm-config",
            "openaps-locald-sync-xdripjs",
        ]
        bin_dir = os.path.join(os.path.dirname(ROOT), "bin")
        for wrapper in wrappers:
            with open(os.path.join(bin_dir, wrapper)) as handle:
                source = handle.read()
            self.assertLess(
                source.index('"/usr/local/src/oref0/openaps-locald"'),
                source.index('"/root/src/oref0/openaps-locald"'),
                wrapper,
            )

    def test_db_dedupes_event_id(self):
        db = EventDB(os.path.join(self.tmp, "events.sqlite3"))
        validated = validate_event(temp_event())
        self.assertTrue(db.insert_event(validated))
        self.assertFalse(db.insert_event(validated))
        self.assertEqual(db.counts()["events"], 1)
        self.assertEqual(db.get_event("evt_1")["event_id"], "evt_1")
        db.close()

    def test_cancel_event_materializes_explicit_cancel_record(self):
        target_path = os.path.join(self.tmp, "settings", "local-temptargets.json")
        cancel_path = os.path.join(self.tmp, "settings", "local-temptarget-cancels.json")
        os.makedirs(os.path.dirname(target_path))
        with open(target_path, "w") as f:
            json.dump([{"eventType": "Temporary Target", "created_at": "2026-04-28T00:00:00Z"}], f)
        config = {
            "rig_id": "rig-demo-1",
            "patient_id": "patient_1",
            "myopenaps_dir": self.tmp,
            "local_temptargets_path": target_path,
            "local_temptarget_cancels_path": cancel_path,
            "materialize_temp_targets": True,
            "materialize_carbs": False,
        }
        result = materialize_event(cancel_event(), config)
        self.assertEqual(result, "materialized_into_temp_target_cancels")
        with open(cancel_path, "r") as f:
            cancel_records = json.load(f)
        self.assertEqual(cancel_records[0]["eventType"], "Temporary Target Cancel")
        self.assertEqual(cancel_records[0]["openaps_app_event_id"], "evt_cancel_1")
        with open(target_path, "r") as f:
            self.assertEqual(json.load(f), [])

    def test_materialization_paths_fall_back_when_config_values_are_null(self):
        config = {
            "myopenaps_dir": self.tmp,
            "local_temptargets_path": None,
            "local_temptarget_cancels_path": None,
            "local_carbhistory_path": None,
            "monitor_carbhistory_path": None,
            "local_glucose_path": None,
            "monitor_glucose_path": None,
            "xdripjs_config_path": os.path.join(self.tmp, "xdripjs.json"),
        }
        state = read_materialization_state(config)
        self.assertTrue(state["temp_targets_path"].endswith("settings/local-temptargets.json"))
        self.assertTrue(state["cancel_audit_path"].endswith("settings/local-temptarget-cancels.json"))

    def test_pumphistory_skips_empty_and_malformed_candidates(self):
        monitor = os.path.join(self.tmp, "monitor")
        os.makedirs(monitor)
        with open(os.path.join(monitor, "pumphistory-merged.json"), "w") as f:
            f.write("")
        with open(os.path.join(monitor, "pumphistory-24h-zoned.json"), "w") as f:
            f.write("not json")
        with open(os.path.join(monitor, "pumphistory-zoned.json"), "w") as f:
            json.dump([{"_type": "Bolus", "amount": 1.0, "timestamp": "2026-04-28T00:00:00Z"}], f)
        payload = read_pumphistory_payload({
            "myopenaps_dir": self.tmp,
            "rig_id": "rig-demo-1",
            "patient_id": "patient_1",
        })
        self.assertEqual(len(payload["bolus_events"]), 1)

    def test_device_status_omits_stale_pump_measurements(self):
        monitor = os.path.join(self.tmp, "monitor")
        os.makedirs(monitor)
        pump_files = {
            "status.json": {"status": "normal", "suspended": False},
            "clock-zoned.json": "2026-04-28T00:00:00-07:00",
            "reservoir.json": 123.4,
            "battery.json": {"status": "normal", "voltage": 1.25, "percent": 75},
        }
        for name, value in pump_files.items():
            with open(os.path.join(monitor, name), "w") as f:
                json.dump(value, f)
        config = {
            "myopenaps_dir": self.tmp,
            "rig_id": "rig-demo-1",
            "patient_id": "patient_1",
        }
        fresh = read_device_status_payload(config)["device_statuses"][0]["pump"]
        self.assertEqual(fresh["clock"], "2026-04-28T00:00:00-07:00")
        self.assertEqual(fresh["reservoir"], 123.4)
        self.assertEqual(fresh["battery"]["percent"], 75)

        enact = os.path.join(self.tmp, "enact")
        os.makedirs(enact)
        with open(os.path.join(enact, "suggested.json"), "w") as f:
            json.dump({
                "bg": 123,
                "reason": "synthetic payload " * 10,
                "predBGs": {"IOB": [123] * 48, "COB": [124] * 48, "UAM": [125] * 48},
            }, f)
        constrained_config = dict(config, ble_device_status_safe_bytes=600)
        constrained = read_device_status_payload(constrained_config)["device_statuses"][0]
        self.assertIn("pump", constrained)
        self.assertLess(len(constrained["openaps"]["suggested"]["predBGs"]["IOB"]), 48)

        stale_at = time.time() - 1900
        for name in ("clock-zoned.json", "reservoir.json", "battery.json"):
            os.utime(os.path.join(monitor, name), (stale_at, stale_at))
        stale = read_device_status_payload(config)["device_statuses"][0]["pump"]
        self.assertNotIn("clock", stale)
        self.assertNotIn("reservoir", stale)
        self.assertNotIn("battery", stale)
        self.assertEqual(stale["status"]["status"], "normal")

    def test_http_post_event_and_duplicate_ack(self):
        nightscout_host = "https://diyps.example.invalid/api/v1?token=placeholder"
        ios_patient_id = _ios_patient_id_from_nightscout(nightscout_host)
        config = {
            "rig_id": "rig_1",
            "patient_id": _patient_id_from_nightscout(nightscout_host),
            "myopenaps_dir": self.tmp,
            "db_path": os.path.join(self.tmp, "events.sqlite3"),
            "bind_host": "127.0.0.1",
            "port": 0,
            "auth_token": None,
            "materialize_temp_targets": False,
            "materialize_carbs": False,
            "nightscout_host": nightscout_host,
        }
        handler = make_handler(config)
        server = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        try:
            port = server.server_address[1]
            body = json.dumps({"events": [temp_event(patient_id=ios_patient_id)]})
            conn = HTTPConnection("127.0.0.1", port)
            conn.request("POST", "/v1/events", body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            conn.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["acks"][0]["ack_status"], "stored")

            conn = HTTPConnection("127.0.0.1", port)
            conn.request("POST", "/v1/events", body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            conn.close()
            self.assertEqual(payload["acks"][0]["ack_status"], "duplicate")
        finally:
            server.shutdown()
            server.server_close()
            handler.db.close()

    def test_http_collector_ack_contains_control_state(self):
        config = self._collector_config()
        config.update({
            "rig_id": "rig_1",
            "patient_id": "patient_1",
            "db_path": os.path.join(self.tmp, "events.sqlite3"),
            "bind_host": "127.0.0.1",
            "port": 0,
            "auth_token": None,
        })
        handler = make_handler(config)
        server = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        started = []
        cron_lines = []
        try:
            with mock.patch.object(collector_control, "_logger_pids", side_effect=lambda: [42] if started else []), mock.patch.object(collector_control, "_start_logger", side_effect=lambda: started.append(True)), mock.patch.object(collector_control, "_read_crontab", side_effect=lambda: list(cron_lines)), mock.patch.object(collector_control, "_install_crontab", side_effect=lambda lines: cron_lines.__setitem__(slice(None), lines)):
                conn = HTTPConnection("127.0.0.1", server.server_address[1])
                conn.request("POST", "/v1/events", body=json.dumps({"events": [collector_event()]}), headers={"Content-Type": "application/json"})
                response = conn.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                conn.close()
                conn = HTTPConnection("127.0.0.1", server.server_address[1])
                conn.request("POST", "/v1/events", body=json.dumps({"events": [collector_event(desired_state="status")]}), headers={"Content-Type": "application/json"})
                duplicate_response = conn.getresponse()
                duplicate_payload = json.loads(duplicate_response.read().decode("utf-8"))
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            handler.db.close()
        details = payload["acks"][0]["details"]
        self.assertEqual(payload["acks"][0]["ack_status"], "stored")
        self.assertEqual(details["desired_state"], "running")
        self.assertEqual(details["actual_state"], "running")
        self.assertEqual(details["transmitter_id"], "ABC123")
        self.assertEqual(details["alternate_bluetooth_channel"], False)
        self.assertEqual(details["election_id"], "election-1")
        self.assertEqual(details["cron_enabled"], True)
        self.assertEqual(details["process_count"], 1)
        duplicate = duplicate_payload["acks"][0]
        self.assertEqual(duplicate["ack_status"], "duplicate")
        self.assertEqual(duplicate["details"]["desired_state"], "status")
        self.assertEqual(duplicate["details"]["actual_state"], "running")
        self.assertEqual(duplicate["details"]["process_count"], 1)


if __name__ == "__main__":
    unittest.main()
