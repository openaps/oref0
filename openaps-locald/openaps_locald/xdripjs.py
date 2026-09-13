from __future__ import print_function

import calendar
import datetime
import json
import os
import re


def _candidate_source_paths(config):
    myopenaps_dir = config["myopenaps_dir"]
    candidates = []
    explicit = config.get("xdripjs_source_path")
    if explicit:
        candidates.append(explicit)
    candidates.extend([
        os.path.join(myopenaps_dir, "monitor", "xdripjs", "entry.json"),
        os.path.join(myopenaps_dir, "monitor", "xdripjs", "last-entry.json"),
        os.path.join(myopenaps_dir, "monitor", "xdripjs", "entry-xdrip.json"),
    ])
    unique = []
    seen = set()
    for path in candidates:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def _read_json(path):
    with open(path, "r") as f:
        return json.load(f)


def _as_list(data):
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _coerce_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str) and value.strip():
        try:
            return int(round(float(value)))
        except Exception:
            return None
    return None


def _iso_from_millis(millis):
    millis = int(millis)
    seconds, ms = divmod(millis, 1000)
    dt = datetime.datetime.utcfromtimestamp(seconds).replace(microsecond=ms * 1000)
    return dt.isoformat() + "Z"


def _record_millis(record):
    for candidate in (record.get("date"), record.get("timestamp")):
        millis = _coerce_int(candidate)
        if millis is not None:
            return millis
    date_string = record.get("dateString")
    if isinstance(date_string, str) and date_string:
        try:
            text = date_string.rstrip("Z")
            if "." in text:
                dt = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f")
            else:
                dt = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
            return int(calendar.timegm(dt.utctimetuple()) * 1000 + (dt.microsecond // 1000))
        except Exception:
            return None
    return None


def read_latest_xdripjs_record(config):
    best = None
    best_path = None
    best_millis = None
    for path in _candidate_source_paths(config):
        if not os.path.exists(path):
            continue
        try:
            records = _as_list(_read_json(path))
        except Exception:
            continue
        for record in records:
            millis = _record_millis(record)
            if millis is None:
                continue
            if best is None or millis > best_millis:
                best = record
                best_path = path
                best_millis = millis
    if best is None:
        return None
    return {
        "source_path": best_path,
        "record": best,
        "date_millis": best_millis,
    }


def _sanitize(value):
    value = value or ""
    value = re.sub(r"[^A-Za-z0-9]+", "_", str(value))
    return value.strip("_") or "unknown"


def bg_event_from_xdripjs_record(record, config, source_path=None):
    date_millis = _record_millis(record)
    if date_millis is None:
        now = datetime.datetime.utcnow()
        date_millis = int(calendar.timegm(now.utctimetuple()) * 1000 + (now.microsecond // 1000))
    date_string = record.get("dateString") or _iso_from_millis(date_millis)
    sgv = _coerce_int(record.get("sgv"))
    if sgv is None:
        sgv = _coerce_int(record.get("glucose"))
    if sgv is None:
        raise ValueError("xdripjs record is missing sgv/glucose")
    source_device_id = config.get("rig_id") or "local"
    transmitter_id = record.get("device")
    event_id = "bg_%013d_%s_%s" % (date_millis, _sanitize(source_device_id), _sanitize(sgv))
    payload = {
        "sgv": sgv,
        "glucose": record.get("glucose", sgv),
        "direction": record.get("direction"),
        "trend": record.get("trend"),
        "trend_rate_mgdl_min": record.get("trend_rate_mgdl_min", record.get("trend_rate_mgdl_minute")),
        "trend_rate_mgdl_minute": record.get("trend_rate_mgdl_minute", record.get("trend_rate_mgdl_min")),
        "filtered": record.get("filtered"),
        "unfiltered": record.get("unfiltered"),
        "rssi": record.get("rssi"),
        "noise": _coerce_int(record.get("noise")),
        "state": record.get("state"),
        "status": record.get("status"),
        "device": transmitter_id,
        "source": "xdripjs",
        "source_device_id": source_device_id,
        "transmitter_id": transmitter_id,
        "collector_channel": "xdripjs",
        "sensor_id": record.get("sensor_id"),
        "raw": record,
    }
    if source_path:
        payload["source_path"] = source_path
    event = {
        "schema": "openaps.local.event.v1",
        "event_id": event_id,
        "patient_id": config["patient_id"],
        "created_at": date_string,
        "effective_at": date_string,
        "created_by_device_id": source_device_id,
        "source": "xdripjs",
        "event_type": "bg_reading",
        "payload": payload,
        "supersedes_event_id": None,
        "signature": None,
    }
    return event


def build_bg_reading_event(config, source_path=None):
    latest = read_latest_xdripjs_record(config)
    if latest is None:
        return None
    event = bg_event_from_xdripjs_record(latest["record"], config, source_path=latest["source_path"])
    if source_path and source_path != latest["source_path"]:
        event["payload"]["source_path"] = source_path
    return event
