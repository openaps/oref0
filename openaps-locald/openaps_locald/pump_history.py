from __future__ import print_function

import calendar
import datetime
import json
import os
import re
import time


PUMPHISTORY_SCHEMA = "openaps.local.pump_history.v1"
DEFAULT_PUMPHISTORY_LIMIT = 288
BLE_SAFE_BYTES = 520
RELEVANT_PUMP_HISTORY_TYPES = set(["TempBasal", "TempBasalDuration", "Bolus", "PumpSuspend", "PumpResume"])
_ISO_TZ_RE = re.compile(r"([+-])(\d\d):(\d\d)$")


def _file_age_seconds(path):
    try:
        return int(time.time() - os.path.getmtime(path))
    except OSError:
        return None


def _candidate_paths(config):
    myopenaps = config["myopenaps_dir"]
    return [
        config.get("monitor_pumphistory_merged_path") or os.path.join(myopenaps, "monitor", "pumphistory-merged.json"),
        config.get("monitor_pumphistory_24h_zoned_path") or os.path.join(myopenaps, "monitor", "pumphistory-24h-zoned.json"),
        config.get("settings_pumphistory_24h_zoned_path") or os.path.join(myopenaps, "settings", "pumphistory-24h-zoned.json"),
        config.get("monitor_pumphistory_zoned_path") or os.path.join(myopenaps, "monitor", "pumphistory-zoned.json"),
        config.get("monitor_pumphistory_path") or os.path.join(myopenaps, "monitor", "pumphistory.json"),
    ]


def _read_json_array(path):
    if not os.path.exists(path):
        return None
    try:
        if os.path.getsize(path) <= 0:
            return None
        with open(path, "r") as f:
            data = json.load(f)
    except (IOError, OSError, ValueError):
        return None
    if isinstance(data, list):
        return data
    return None


def _selected_pumphistory(config):
    candidates = _candidate_paths(config)
    for path in candidates:
        records = _read_json_array(path)
        if records is not None:
            return path, records, candidates
    return None, [], candidates


def read_pumphistory_records(config, limit=DEFAULT_PUMPHISTORY_LIMIT):
    _source_path, records, _ = _selected_pumphistory(config)
    return _limit_records(records, limit)


def _limit_records(records, limit):
    if limit is None:
        return records
    try:
        limit = int(limit)
    except Exception:
        limit = DEFAULT_PUMPHISTORY_LIMIT
    if limit <= 0:
        return []
    if limit >= len(records):
        return records
    indexed = []
    for index, record in enumerate(records):
        millis = _record_timestamp_millis(record)
        indexed.append(((millis if millis is not None else -1), index, record))
    indexed.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [item[2] for item in indexed[:limit]]


def _first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _coerce_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except Exception:
            return None
    return None


def _iso_to_millis(value):
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    offset_minutes = 0
    if text.endswith("Z"):
        text = text[:-1]
    else:
        match = _ISO_TZ_RE.search(text)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            offset_minutes = sign * (int(match.group(2)) * 60 + int(match.group(3)))
            text = text[:-6]
    try:
        if "." in text:
            dt = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None
    return int(calendar.timegm(dt.utctimetuple()) * 1000 + (dt.microsecond // 1000) - (offset_minutes * 60 * 1000))


def _millis_to_iso(millis):
    if millis is None:
        return None
    millis = int(millis)
    seconds, ms = divmod(millis, 1000)
    dt = datetime.datetime.utcfromtimestamp(seconds).replace(microsecond=ms * 1000)
    return dt.isoformat() + "Z"


def _record_timestamp_millis(record):
    for candidate in (
        record.get("timestamp"),
        record.get("dateString"),
        record.get("created_at"),
        record.get("date"),
    ):
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, (int, float)):
            return int(candidate)
        millis = _iso_to_millis(candidate)
        if millis is not None:
            return millis
    return None


def _record_timestamp(record):
    return _first_non_empty(
        record.get("timestamp"),
        record.get("dateString"),
        record.get("created_at"),
        _millis_to_iso(_record_timestamp_millis(record)),
    )


def _record_group_key(record):
    for candidate in ("timestamp", "dateString", "created_at", "_date"):
        value = record.get(candidate)
        if value not in (None, ""):
            return "%s=%s" % (candidate, value)
    return None


def _records_in_time_order(records):
    indexed = []
    for index, record in enumerate(records):
        millis = _record_timestamp_millis(record)
        indexed.append(((millis if millis is not None else -1), index, record))
    indexed.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in indexed]


def _sort_events_desc(events, key_name):
    def _sort_key(event):
        millis = _iso_to_millis(event.get(key_name))
        return millis if millis is not None else -1

    return sorted(events, key=_sort_key, reverse=True)


def _copy_if_present(target, source, key, out_key=None):
    value = source.get(key)
    if value not in (None, ""):
        target[out_key or key] = value


def _temp_basal_event(temp_record, duration_record=None):
    timestamp = _record_timestamp(temp_record)
    duration_minutes = None
    if duration_record is not None:
        duration_minutes = duration_record.get("duration (min)")
    if duration_minutes is None:
        duration_minutes = temp_record.get("duration_minutes")
    if duration_minutes is None:
        duration_minutes = temp_record.get("duration")
    duration_minutes = _coerce_float(duration_minutes)
    rate = _coerce_float(temp_record.get("rate"))
    units = None
    if rate is not None and duration_minutes is not None:
        units = round(rate * duration_minutes / 60.0, 3)
    elif rate is not None:
        units = rate
    event = {
        "event_type": "temp_basal",
        "date": timestamp,
        "units": units,
        "duration_minutes": duration_minutes,
        "rate": rate,
    }
    _copy_if_present(event, temp_record, "temp")
    _copy_if_present(event, temp_record, "id", "pump_event_id")
    if duration_record is not None:
        _copy_if_present(event, duration_record, "id", "duration_event_id")
    event["pump_event_type"] = temp_record.get("_type") or "TempBasal"
    if duration_record is not None:
        event["duration_event_type"] = duration_record.get("_type") or "TempBasalDuration"
    return event


def _bolus_event(record):
    timestamp = _record_timestamp(record)
    units = _coerce_float(record.get("amount"))
    if units is None:
        units = _coerce_float(record.get("programmed"))
    if units is None:
        return None
    event = {
        "event_type": "bolus",
        "date": timestamp,
        "units": units,
    }
    _copy_if_present(event, record, "amount")
    _copy_if_present(event, record, "programmed")
    _copy_if_present(event, record, "duration")
    _copy_if_present(event, record, "unabsorbed")
    _copy_if_present(event, record, "id", "pump_event_id")
    event["pump_event_type"] = record.get("_type") or "Bolus"
    return event


def _pump_suspend_segment(start_date, end_date):
    return {
        "event_type": "pump_suspend_segment",
        "start_date": start_date,
        "end_date": end_date,
    }


def _json_size(payload):
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _build_pumphistory_object(config, records, source_count=None, partial=False, max_bytes=None):
    ordered = _records_in_time_order(records)
    temp_basal_records = {}
    temp_basal_duration_records = {}
    insulin_events = []
    bolus_events = []
    pump_suspend_segments = []
    suspend_start = None

    for record in ordered:
        record_type = record.get("_type")
        timestamp = _record_timestamp(record)
        group_key = _record_group_key(record)
        if record_type == "TempBasal":
            temp_basal_records.setdefault(group_key, []).append(record)
        elif record_type == "TempBasalDuration":
            temp_basal_duration_records.setdefault(group_key, []).append(record)
        elif record_type == "PumpSuspend":
            if suspend_start is None:
                suspend_start = timestamp
        elif record_type == "PumpResume":
            if suspend_start is not None:
                pump_suspend_segments.append(_pump_suspend_segment(suspend_start, timestamp))
                suspend_start = None
        elif record_type == "Bolus":
            bolus_event = _bolus_event(record)
            if bolus_event is not None:
                bolus_events.append(bolus_event)

    for group_key, pending_records in temp_basal_records.items():
        duration_records = temp_basal_duration_records.get(group_key) or []
        for index, temp_record in enumerate(pending_records):
            duration_record = duration_records[index] if index < len(duration_records) else None
            event = _temp_basal_event(temp_record, duration_record)
            if event.get("units") is not None and event.get("duration_minutes") is not None:
                insulin_events.append(event)

    if suspend_start is not None:
        pump_suspend_segments.append(_pump_suspend_segment(suspend_start, None))

    generated_at = _millis_to_iso(int(calendar.timegm(datetime.datetime.utcnow().utctimetuple()) * 1000))
    return {
        "schema": PUMPHISTORY_SCHEMA,
        "rig_id": config.get("rig_id"),
        "patient_id": config.get("patient_id"),
        "generated_at": generated_at,
        "partial": bool(partial),
        "source_record_count": source_count if source_count is not None else len(records),
        "selected_record_count": len(records),
        "max_bytes": max_bytes,
        "insulin_events": _sort_events_desc(insulin_events, "date"),
        "pump_suspend_segments": _sort_events_desc(pump_suspend_segments, "start_date"),
        "bolus_events": _sort_events_desc(bolus_events, "date"),
    }


def _event_sort_millis(event, key_name):
    millis = _iso_to_millis(event.get(key_name))
    return millis if millis is not None else -1


def _fit_pumphistory_payload(payload, max_bytes):
    if _json_size(payload) <= max_bytes:
        return payload
    base = {
        "schema": payload.get("schema"),
        "rig_id": payload.get("rig_id"),
        "patient_id": payload.get("patient_id"),
        "generated_at": payload.get("generated_at"),
        "partial": True,
    }
    items = []
    for key, date_key in (
        ("insulin_events", "date"),
        ("pump_suspend_segments", "start_date"),
        ("bolus_events", "date"),
    ):
        for event in payload.get(key) or []:
            items.append((_event_sort_millis(event, date_key), key, event))
    items.sort(key=lambda item: item[0], reverse=True)
    for count in range(len(items), -1, -1):
        candidate = dict(base)
        candidate["insulin_events"] = []
        candidate["pump_suspend_segments"] = []
        candidate["bolus_events"] = []
        for _millis, key, event in items[:count]:
            candidate[key].append(event)
        candidate["insulin_events"] = _sort_events_desc(candidate["insulin_events"], "date")
        candidate["pump_suspend_segments"] = _sort_events_desc(candidate["pump_suspend_segments"], "start_date")
        candidate["bolus_events"] = _sort_events_desc(candidate["bolus_events"], "date")
        if _json_size(candidate) <= max_bytes:
            return candidate
    compact_items = []
    for millis, key, event in items:
        if key == "insulin_events":
            keep = ["event_type", "date", "rate", "temp", "duration_minutes", "units"]
        elif key == "bolus_events":
            keep = ["event_type", "date", "units", "amount", "programmed", "duration", "unabsorbed"]
        else:
            keep = ["event_type", "start_date", "end_date"]
        compact_items.append((millis, key, {name: event[name] for name in keep if name in event}))
    for count in range(len(compact_items), -1, -1):
        candidate = dict(base)
        candidate["insulin_events"] = []
        candidate["pump_suspend_segments"] = []
        candidate["bolus_events"] = []
        for _millis, key, event in compact_items[:count]:
            candidate[key].append(event)
        candidate["insulin_events"] = _sort_events_desc(candidate["insulin_events"], "date")
        candidate["pump_suspend_segments"] = _sort_events_desc(candidate["pump_suspend_segments"], "start_date")
        candidate["bolus_events"] = _sort_events_desc(candidate["bolus_events"], "date")
        if _json_size(candidate) <= max_bytes:
            return candidate
    candidate = dict(base)
    candidate["insulin_events"] = []
    candidate["pump_suspend_segments"] = []
    candidate["bolus_events"] = []
    return candidate


def read_pumphistory_summary(config):
    source_path, records, candidates = _selected_pumphistory(config)
    age_seconds = _file_age_seconds(source_path) if source_path else None
    return {
        "candidate_paths": candidates,
        "source_path": source_path,
        "available": source_path is not None,
        "entry_count": len(records),
        "age_seconds": age_seconds,
        "fresh": age_seconds is not None and age_seconds <= 900,
    }


def read_pumphistory_payload(config, limit=DEFAULT_PUMPHISTORY_LIMIT, max_bytes=None):
    _source_path, records, _candidates = _selected_pumphistory(config)
    selected_records = _limit_records(records, limit)
    partial = len(selected_records) < len(records)
    if max_bytes is None:
        return _build_pumphistory_object(config, selected_records, source_count=len(records), partial=partial)
    relevant_records = [
        record for record in selected_records
        if record.get("_type") in RELEVANT_PUMP_HISTORY_TYPES
    ]
    max_bytes = int(max_bytes)
    payload = _build_pumphistory_object(
        config,
        relevant_records,
        source_count=len(records),
        partial=True,
        max_bytes=max_bytes,
    )
    return _fit_pumphistory_payload(payload, max_bytes)
