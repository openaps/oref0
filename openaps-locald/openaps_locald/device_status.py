from __future__ import print_function

import json
import os
from datetime import datetime

from .pump_history import read_pumphistory_payload


DEVICE_STATUS_SCHEMA = "openaps.local.device_status.v1"
DEFAULT_PRED_BG_POINTS = 48
BLE_SAFE_BYTES = 4096
PUMP_STATUS_MAX_AGE_SECONDS = 1800

_SUGGESTED_KEYS = [
    "temp",
    "bg",
    "tick",
    "eventualBG",
    "insulinReq",
    "sensitivityRatio",
    "COB",
    "IOB",
    "BGI",
    "deviation",
    "ISF",
    "CR",
    "target_bg",
    "rate",
    "duration",
]

_ENACTED_KEYS = _SUGGESTED_KEYS + ["received"]


def _utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _file_age_seconds(path):
    try:
        return int((datetime.utcnow() - datetime.utcfromtimestamp(os.path.getmtime(path))).total_seconds())
    except OSError:
        return None


def _read_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _file_entry(path):
    data = _read_json(path)
    result = {
        "path": path,
        "age_seconds": _file_age_seconds(path),
        "available": data is not None,
    }
    if data is not None:
        result["data"] = data
    return result


def _fresh_file_data(entry, max_age_seconds):
    if not entry.get("available"):
        return None
    age = entry.get("age_seconds")
    if age is not None and age > max_age_seconds:
        return None
    return entry.get("data")


def _relative_file(config, *parts):
    return os.path.join(config["myopenaps_dir"], *parts)


def _trim_pred_bgs(pred_bgs, limit):
    if not isinstance(pred_bgs, dict):
        return None
    trimmed = {}
    for key, values in pred_bgs.items():
        if isinstance(values, list):
            trimmed[key] = values[:limit]
    return trimmed or None


def _compact_loop_payload(payload, keys, pred_limit):
    if not isinstance(payload, dict):
        return payload
    result = {key: payload[key] for key in keys if key in payload}
    pred_bgs = _trim_pred_bgs(payload.get("predBGs"), pred_limit)
    if pred_bgs:
        result["predBGs"] = pred_bgs
        result["predBGs_truncated"] = True
        result["predBGs_points"] = pred_limit
    return result


def _json_size(payload):
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _payload(record, config, generated_at):
    return {
        "schema": DEVICE_STATUS_SCHEMA,
        "device_statuses": [record],
    }


def _candidate_pred_limits(current_limit):
    limits = []
    for value in (current_limit, 36, 24, 18, 12, 6, 4, 2):
        try:
            value = int(value)
        except Exception:
            continue
        if value > 0 and value not in limits:
            limits.append(value)
    return limits


def _apply_pred_limit(suggested, limit):
    pred_bgs = suggested.get("predBGs") or {}
    for key, values in list(pred_bgs.items()):
        if isinstance(values, list):
            pred_bgs[key] = values[:limit]
    suggested["predBGs_truncated"] = True
    suggested["predBGs_points"] = limit


def _fit_for_ble(record, config, generated_at):
    safe_bytes = int(config.get("ble_device_status_safe_bytes") or BLE_SAFE_BYTES)
    payload = _payload(record, config, generated_at)
    if _json_size(payload) <= safe_bytes:
        return payload

    openaps = record.get("openaps") or {}
    for key in ["meal", "iob", "enacted"]:
        openaps.pop(key, None)
        payload = _payload(record, config, generated_at)
        if _json_size(payload) <= safe_bytes:
            return payload

    suggested = openaps.get("suggested") or {}
    pred_bgs = suggested.get("predBGs") or {}
    current_limit = suggested.get("predBGs_points") or DEFAULT_PRED_BG_POINTS
    for limit in _candidate_pred_limits(current_limit):
        _apply_pred_limit(suggested, limit)
        payload = _payload(record, config, generated_at)
        if _json_size(payload) <= safe_bytes:
            return payload

    suggested.pop("predBGs", None)
    suggested.pop("predBGs_truncated", None)
    suggested.pop("predBGs_points", None)
    payload = _payload(record, config, generated_at)
    if _json_size(payload) <= safe_bytes:
        return payload

    record.pop("pump", None)
    return _payload(record, config, generated_at)


def _compact_iob(payload):
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        first = payload[0]
    elif isinstance(payload, dict):
        first = payload
    else:
        return None
    return {key: first[key] for key in ["iob", "activity", "bolussnooze"] if key in first}


def _compact_meal(payload):
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ["carbs", "mealCOB", "COB", "bwFound"]
        if key in payload
    }


def _compact_pump_status(payload):
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ["status", "bolusing", "suspended"]
        if key in payload
    }


def _infer_pump_suspended(config):
    try:
        payload = read_pumphistory_payload(config, limit=200)
    except Exception:
        return None
    segments = payload.get("pump_suspend_segments") or []
    if not segments:
        return None
    for segment in segments:
        if segment.get("end_date") in (None, ""):
            return True
    return False


def _pump_status_with_suspend_fallback(config, payload):
    status = _compact_pump_status(payload)
    if not isinstance(status, dict):
        status = {}
    if "suspended" not in status:
        suspended = _infer_pump_suspended(config)
        if suspended is not None:
            status["suspended"] = suspended
    return status or None


def _pump_status_max_age_seconds(config):
    try:
        return int(config.get("ble_pump_status_max_age_seconds") or PUMP_STATUS_MAX_AGE_SECONDS)
    except Exception:
        return PUMP_STATUS_MAX_AGE_SECONDS


def _pump_clock(files, max_age_seconds):
    clock = _fresh_file_data(files["pump_clock_zoned"], max_age_seconds)
    if clock not in (None, "", {}):
        return clock
    return _fresh_file_data(files["pump_clock"], max_age_seconds)


def _pump_battery(payload):
    if isinstance(payload, dict):
        return {
            key: payload[key]
            for key in ["status", "voltage", "percent"]
            if key in payload
        } or None
    return payload


def _prune_empty(value):
    if isinstance(value, dict):
        pruned = {}
        for key, item in value.items():
            compact = _prune_empty(item)
            if compact not in (None, {}, []):
                pruned[key] = compact
        return pruned
    if isinstance(value, list):
        return [_prune_empty(item) for item in value if _prune_empty(item) not in (None, {}, [])]
    return value


def read_device_status_payload(config):
    """Return loop/devicestatus data the phone needs while offline."""
    files = {
        "suggested": _file_entry(_relative_file(config, "enact", "suggested.json")),
        "enacted": _file_entry(_relative_file(config, "enact", "enacted.json")),
        "pump_status": _file_entry(_relative_file(config, "monitor", "status.json")),
        "pump_clock_zoned": _file_entry(_relative_file(config, "monitor", "clock-zoned.json")),
        "pump_clock": _file_entry(_relative_file(config, "monitor", "clock.json")),
        "pump_reservoir": _file_entry(_relative_file(config, "monitor", "reservoir.json")),
        "pump_battery": _file_entry(_relative_file(config, "monitor", "battery.json")),
        "iob": _file_entry(_relative_file(config, "monitor", "iob.json")),
        "meal": _file_entry(_relative_file(config, "monitor", "meal.json")),
        "glucose": _file_entry(_relative_file(config, "monitor", "glucose.json")),
        "local_glucose": _file_entry(_relative_file(config, "monitor", "local-glucose.json")),
        "temp_basal": _file_entry(_relative_file(config, "monitor", "temp_basal.json")),
    }
    pred_limit = int(config.get("ble_device_status_pred_points") or DEFAULT_PRED_BG_POINTS)
    pump_max_age_seconds = _pump_status_max_age_seconds(config)
    generated_at = _utc_now()
    record = {
        "device": "openaps://%s" % config["rig_id"],
        "created_at": generated_at,
        "openaps": _prune_empty({
            "suggested": _compact_loop_payload(files["suggested"].get("data"), _SUGGESTED_KEYS, pred_limit),
            "enacted": _compact_loop_payload(files["enacted"].get("data"), _ENACTED_KEYS, pred_limit),
            "iob": _compact_iob(files["iob"].get("data")),
            "meal": _compact_meal(files["meal"].get("data")),
        }),
        "pump": _prune_empty({
            "status": _pump_status_with_suspend_fallback(config, files["pump_status"].get("data")),
            "clock": _pump_clock(files, pump_max_age_seconds),
            "reservoir": _fresh_file_data(files["pump_reservoir"], pump_max_age_seconds),
            "battery": _pump_battery(_fresh_file_data(files["pump_battery"], pump_max_age_seconds)),
        }),
    }
    return _fit_for_ble(record, config, generated_at)
