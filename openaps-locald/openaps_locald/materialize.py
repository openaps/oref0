from __future__ import print_function

import json
import os
import tempfile
import subprocess

from .bg_history import merge_local_bg_into_monitor, read_bg_materialization_state, write_local_bg_record
from .carb_history import merge_local_carbs_into_monitor, read_carb_materialization_state, write_local_carb_record
from .collector_control import apply_collector_control, read_collector_status
from .xdripjs_config import read_xdripjs_config_state, update_xdripjs_settings


def _materialize_log(message):
    print("[materialize] %s" % message, flush=True)


def _local_temptargets_path(config):
    return config.get("local_temptargets_path") or os.path.join(config["myopenaps_dir"], "settings", "local-temptargets.json")


def _local_temptarget_cancels_path(config):
    return config.get("local_temptarget_cancels_path") or os.path.join(config["myopenaps_dir"], "settings", "local-temptarget-cancels.json")


def _read_json_array(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return []


def _describe_json_array(path):
    if not os.path.exists(path):
        return "missing"
    try:
        data = _read_json_array(path)
    except Exception as exc:
        return "unreadable error=%s" % exc
    return "exists count=%d size=%d" % (len(data), os.path.getsize(path))


def read_materialization_state(config):
    temp_targets_path = _local_temptargets_path(config)
    cancel_path = _local_temptarget_cancels_path(config)
    carb_state = read_carb_materialization_state(config)
    bg_state = read_bg_materialization_state(config)
    xdripjs_state = read_xdripjs_config_state(config)
    collector_state = read_collector_status(config)
    return {
        "temp_targets_path": temp_targets_path,
        "cancel_audit_path": cancel_path,
        "temp_targets": _read_json_array(temp_targets_path),
        "cancel_audits": _read_json_array(cancel_path),
        "carbs_path": carb_state["local_carbhistory_path"],
        "monitor_carbhistory_path": carb_state["monitor_carbhistory_path"],
        "carbs": carb_state["local_carbs"],
        "monitor_carbs": carb_state["monitor_carbs"],
        "merged_carbs_preview": carb_state["merged_carbs_preview"],
        "carbs_count": carb_state["local_carbs_count"],
        "monitor_carbs_count": carb_state["monitor_carbs_count"],
        "merged_carbs_count": carb_state["merged_carbs_count"],
        "bg_path": bg_state["local_glucose_path"],
        "monitor_bg_path": bg_state["monitor_glucose_path"],
        "bg_readings": bg_state["local_glucose"],
        "monitor_bg_readings": bg_state["monitor_glucose"],
        "merged_bg_preview": bg_state["merged_glucose_preview"],
        "bg_count": bg_state["local_glucose_count"],
        "monitor_bg_count": bg_state["monitor_glucose_count"],
        "merged_bg_count": bg_state["merged_glucose_count"],
        "xdripjs_config_path": xdripjs_state["xdripjs_config_path"],
        "xdripjs_config_exists": xdripjs_state["xdripjs_config_exists"],
        "xdripjs_transmitter_id": xdripjs_state["xdripjs_transmitter_id"],
        "xdripjs_config_error": xdripjs_state.get("xdripjs_config_error"),
        "collector": collector_state,
    }


def _atomic_write_json(path, payload):
    dirname = os.path.dirname(path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    fd, tmp_path = tempfile.mkstemp(prefix=".openaps-locald-", suffix=".json", dir=dirname or None)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, sort_keys=True, indent=2)
            f.write("\n")
        os.rename(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _append_local_record(path, record):
    records = _read_json_array(path)
    records.insert(0, record)
    _atomic_write_json(path, records)


def _clear_local_temptargets(path):
    _atomic_write_json(path, [])


def _ensure_local_temptargets(path):
    if os.path.exists(path):
        return
    _materialize_log("bootstrap temp-target file path=%s" % path)
    _atomic_write_json(path, [])


def _temp_target_cancel_record(event):
    created_at = event.get("effective_at") or event.get("created_at")
    event_id = event.get("event_id")
    record = {
        "eventType": "Temporary Target Cancel",
        "created_at": created_at,
        "enteredBy": "OpenAPS iOS",
        "utcOffset": 0,
        "carbs": None,
        "insulin": None,
    }
    if event_id:
        notes = "openaps_app_event_id=%s" % event_id
        record["notes"] = notes
        record["openapsAppEventId"] = event_id
        record["openaps_app_event_id"] = event_id
    return record


def _materialize_event(event, config):
    event_type = event.get("event_type")
    if event_type == "temp_target":
        if not config.get("materialize_temp_targets"):
            return "stored_not_materialized"
        payload = event["payload"]
        target = int(round((payload["target_bottom_mgdl"] + payload["target_top_mgdl"]) / 2.0))
        duration = int(payload["duration_minutes"])
        effective_at = event.get("effective_at")
        temp_targets_path = _local_temptargets_path(config)
        _materialize_log(
            "temp_target event_id=%s target=%s duration=%s effective_at=%s path=%s before=%s"
            % (event.get("event_id"), target, duration, effective_at, temp_targets_path, _describe_json_array(temp_targets_path))
        )
        args = ["oref0-append-local-temptarget", str(target), str(duration)]
        if effective_at:
            args.append(effective_at)
        # The upstream append helper expects the local temp-target file to already exist.
        _ensure_local_temptargets(temp_targets_path)
        _materialize_log("temp_target after bootstrap path=%s state=%s" % (temp_targets_path, _describe_json_array(temp_targets_path)))
        _materialize_log("temp_target append invoke cwd=%s args=%s" % (config["myopenaps_dir"], args))
        try:
            subprocess.check_call(args, cwd=config["myopenaps_dir"])
        except Exception as exc:
            _materialize_log("temp_target append failed path=%s error=%s state=%s" % (temp_targets_path, exc, _describe_json_array(temp_targets_path)))
            raise
        _materialize_log("temp_target append complete path=%s state=%s" % (temp_targets_path, _describe_json_array(temp_targets_path)))
        return "materialized_into_temp_targets"
    if event_type == "cancel_temp_target":
        if not config.get("materialize_temp_targets"):
            return "stored_not_materialized"
        temp_targets_path = _local_temptargets_path(config)
        cancel_path = _local_temptarget_cancels_path(config)
        _materialize_log(
            "cancel_temp_target event_id=%s temp_path=%s before_temp=%s before_cancel=%s"
            % (event.get("event_id"), temp_targets_path, _describe_json_array(temp_targets_path), _describe_json_array(cancel_path))
        )
        _append_local_record(cancel_path, _temp_target_cancel_record(event))
        _clear_local_temptargets(temp_targets_path)
        _materialize_log(
            "cancel_temp_target complete temp_path=%s after_temp=%s cancel_path=%s after_cancel=%s"
            % (temp_targets_path, _describe_json_array(temp_targets_path), cancel_path, _describe_json_array(cancel_path))
        )
        return "materialized_into_temp_target_cancels"
    if event_type == "carb_entry":
        if not config.get("materialize_carbs"):
            return "stored_not_materialized"
        write_local_carb_record(event, config)
        if config.get("merge_local_carbs_into_monitor"):
            merge_local_carbs_into_monitor(config)
        return "materialized_into_local_carbhistory"
    if event_type == "bg_reading":
        if not config.get("materialize_bg_readings"):
            return "stored_not_materialized"
        write_local_bg_record(event, config)
        if config.get("merge_local_bg_into_monitor"):
            merge_local_bg_into_monitor(config)
            return "materialized_into_monitor_glucose"
        return "materialized_into_local_glucose"
    if event_type == "set_cgm_config":
        payload = event.get("payload", {})
        collector = payload.get("collector") or "xdripjs"
        transmitter_id = payload.get("transmitter_id")
        alternate = payload.get("alternate_bluetooth_channel")
        if collector != "xdripjs" or (transmitter_id is None and alternate is None):
            return "stored_not_materialized"
        xdripjs_state_before = read_xdripjs_config_state(config)
        _materialize_log(
            "set_cgm_config event_id=%s path=%s before_tx=%s new_tx=%s"
            % (event.get("event_id"), xdripjs_state_before["xdripjs_config_path"], xdripjs_state_before.get("xdripjs_transmitter_id"), transmitter_id)
        )
        update_xdripjs_settings(config, transmitter_id, alternate)
        _materialize_log(
            "set_cgm_config complete path=%s after_tx=%s"
            % (xdripjs_state_before["xdripjs_config_path"], transmitter_id)
        )
        return "materialized_into_xdripjs_config"
    return "stored_not_materialized"


def materialize_event_result(event, config):
    if event.get("event_type") == "cgm_collector_control":
        return apply_collector_control(config, event["payload"])
    return {"materialization": _materialize_event(event, config)}


def collector_ack_details(event, config):
    if event.get("event_type") != "cgm_collector_control":
        return {}
    return read_collector_status(config, event.get("payload"))


def materialize_event(event, config):
    return materialize_event_result(event, config)["materialization"]
