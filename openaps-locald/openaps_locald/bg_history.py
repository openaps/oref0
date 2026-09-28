from __future__ import print_function

import calendar
import datetime
import json
import os
import tempfile


def _local_glucose_path(config):
    return config.get("local_glucose_path") or os.path.join(config["myopenaps_dir"], "monitor", "local-glucose.json")


def _monitor_glucose_path(config):
    return config.get("monitor_glucose_path") or os.path.join(config["myopenaps_dir"], "monitor", "glucose.json")


def _read_json_array(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return []


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


def _first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _iso_to_millis(value):
    if not isinstance(value, str) or not value:
        return None
    text = value.rstrip("Z")
    try:
        if "." in text:
            dt = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None
    return int(calendar.timegm(dt.utctimetuple()) * 1000 + (dt.microsecond // 1000))


def _millis_to_iso(millis):
    if millis is None:
        return None
    millis = int(millis)
    seconds, ms = divmod(millis, 1000)
    dt = datetime.datetime.utcfromtimestamp(seconds).replace(microsecond=ms * 1000)
    return dt.isoformat() + "Z"


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


def _bg_event_time(event, payload):
    for candidate in (
        payload.get("dateString"),
        event.get("effective_at"),
        event.get("created_at"),
    ):
        millis = _iso_to_millis(candidate)
        if millis is not None:
            return millis
    return int(calendar.timegm(datetime.datetime.utcnow().utctimetuple()) * 1000)


def _bg_event_iso(event, payload, date_millis):
    return _first_non_empty(
        payload.get("dateString"),
        event.get("effective_at"),
        event.get("created_at"),
        _millis_to_iso(date_millis),
    )


def bg_record_from_event(event):
    payload = event.get("payload") or {}
    source = _first_non_empty(payload.get("source"), event.get("source"), "bg_reading")
    source_device_id = _first_non_empty(payload.get("source_device_id"), event.get("created_by_device_id"))
    transmitter_id = _first_non_empty(payload.get("transmitter_id"), payload.get("device"))
    date_millis = _bg_event_time(event, payload)
    date_string = _bg_event_iso(event, payload, date_millis)
    sgv = _coerce_int(payload.get("sgv"))
    glucose = _coerce_int(payload.get("glucose"))
    if glucose is None:
        glucose = sgv
    device = payload.get("device")
    if source == "xdripjs" and source_device_id:
        device = "xdripjs://%s" % source_device_id
    trend_rate = _first_non_empty(
        payload.get("trend_rate_mgdl_minute"),
        payload.get("trend_rate_mgdl_min"),
    )
    record = {
        "date": date_millis,
        "dateString": date_string,
        "sgv": sgv,
        "glucose": glucose,
        "direction": payload.get("direction"),
        "type": "sgv",
        "filtered": payload.get("filtered"),
        "unfiltered": payload.get("unfiltered"),
        "rssi": payload.get("rssi"),
        "noise": payload.get("noise"),
        "trend": payload.get("trend"),
        "trend_rate_mgdl_min": trend_rate,
        "trend_rate_mgdl_minute": trend_rate,
        "state": payload.get("state"),
        "status": payload.get("status"),
        "device": device or transmitter_id or source,
        "source": source,
        "source_device_id": source_device_id,
        "collector_channel": _first_non_empty(payload.get("collector_channel"), source),
        "transmitter_id": transmitter_id,
        "sensor_id": payload.get("sensor_id"),
        "received_at": event.get("received_at") or _millis_to_iso(date_millis),
    }
    event_id = event.get("event_id")
    if event_id:
        record["openapsAppEventId"] = event_id
        record["openaps_app_event_id"] = event_id
    notes = payload.get("notes")
    if notes is not None:
        record["notes"] = notes
    return record


def _record_identity_candidates(record):
    candidates = []
    for key in ("openaps_app_event_id", "openapsAppEventId", "reading_id", "event_id"):
        value = record.get(key)
        if value not in (None, ""):
            candidates.append("%s=%s" % (key, value))
    date = record.get("date")
    glucose = record.get("glucose", record.get("sgv"))
    device = record.get("device")
    if date not in (None, "") and glucose not in (None, "") and device not in (None, ""):
        candidates.append("date+glucose+device=%s|%s|%s" % (date, glucose, device))
    date_string = record.get("dateString")
    if date_string not in (None, "") and glucose not in (None, "") and device not in (None, ""):
        candidates.append("dateString+glucose+device=%s|%s|%s" % (date_string, glucose, device))
    return candidates


def _record_timestamp_millis(record):
    date = _coerce_int(record.get("date"))
    if date is not None:
        return date
    return _iso_to_millis(record.get("dateString")) or -1


def merge_bg_records(local_records, monitor_records):
    merged = []
    seen = set()
    for source_records in (local_records, monitor_records):
        for record in source_records:
            candidates = _record_identity_candidates(record)
            if any(candidate in seen for candidate in candidates):
                continue
            merged.append(record)
            seen.update(candidates)
    # oref0 reads the first monitor/glucose.json entry as the current BG.
    # Local BLE events can arrive out of order (for example, a backlog after
    # reconnect), so source-array order must never determine the loop's BG.
    return sorted(merged, key=_record_timestamp_millis, reverse=True)


def write_local_bg_record(event, config):
    path = _local_glucose_path(config)
    records = _read_json_array(path)
    records.insert(0, bg_record_from_event(event))
    _atomic_write_json(path, sorted(records, key=_record_timestamp_millis, reverse=True))
    return path


def merge_local_bg_into_monitor(config):
    local_path = _local_glucose_path(config)
    monitor_path = _monitor_glucose_path(config)
    local_records = _read_json_array(local_path)
    monitor_records = _read_json_array(monitor_path)
    merged = merge_bg_records(local_records, monitor_records)
    _atomic_write_json(monitor_path, merged)
    return {
        "local_path": local_path,
        "monitor_path": monitor_path,
        "merged_count": len(merged),
        "local_count": len(local_records),
        "monitor_count": len(monitor_records),
    }


def read_bg_materialization_state(config):
    local_path = _local_glucose_path(config)
    monitor_path = _monitor_glucose_path(config)
    local_records = _read_json_array(local_path)
    monitor_records = _read_json_array(monitor_path)
    merged = merge_bg_records(local_records, monitor_records)
    return {
        "local_glucose_path": local_path,
        "monitor_glucose_path": monitor_path,
        "local_glucose": local_records,
        "monitor_glucose": monitor_records,
        "merged_glucose_preview": merged[:20],
        "local_glucose_count": len(local_records),
        "monitor_glucose_count": len(monitor_records),
        "merged_glucose_count": len(merged),
    }
