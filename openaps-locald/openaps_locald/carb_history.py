from __future__ import print_function

import json
import os
import tempfile


def _local_carbhistory_path(config):
    return config.get("local_carbhistory_path") or os.path.join(config["myopenaps_dir"], "monitor", "local-carbhistory.json")


def _monitor_carbhistory_path(config):
    return config.get("monitor_carbhistory_path") or os.path.join(config["myopenaps_dir"], "monitor", "carbhistory.json")


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


def _carb_notes(event):
    payload = event.get("payload") or {}
    notes = payload.get("notes")
    event_id = event.get("event_id")
    marker = "openaps_app_event_id=%s" % event_id if event_id else None
    if notes:
        if marker and marker not in notes:
            return marker + "; " + notes
        return notes
    return marker


def carb_record_from_event(event):
    payload = event.get("payload") or {}
    carbs = payload.get("carbs_g")
    created_at = _first_non_empty(event.get("effective_at"), event.get("created_at"))
    event_id = event.get("event_id")
    record = {
        "eventType": payload.get("nightscout_event_type") or "Carb Correction",
        "carbs": carbs,
        "created_at": created_at,
        "enteredBy": "OpenAPS iOS",
        "units": "mg/dl",
    }
    notes = _carb_notes(event)
    if notes:
        record["notes"] = notes
    if event_id:
        record["openapsAppEventId"] = event_id
        record["openaps_app_event_id"] = event_id
    return record


def _dedupe_key_candidates(record):
    candidates = []
    for key in ("openaps_app_event_id", "openapsAppEventId", "identifier", "_id"):
        value = record.get(key)
        if value not in (None, ""):
            candidates.append((key, value))
    created_at = record.get("created_at")
    carbs = record.get("carbs")
    if created_at not in (None, "") and carbs not in (None, ""):
        candidates.append(("created_at+carbs", "%s|%s" % (created_at, carbs)))
    return candidates


def merge_carbhistory_records(local_records, remote_records):
    merged = []
    seen = set()
    for source_records in (local_records, remote_records):
        for record in source_records:
            candidates = _dedupe_key_candidates(record)
            duplicate = False
            for candidate in candidates:
                if candidate in seen:
                    duplicate = True
                    break
            if duplicate:
                continue
            merged.append(record)
            for candidate in candidates:
                seen.add(candidate)
    return merged


def write_local_carb_record(event, config):
    path = _local_carbhistory_path(config)
    records = _read_json_array(path)
    records.insert(0, carb_record_from_event(event))
    _atomic_write_json(path, records)
    return path


def merge_local_carbs_into_monitor(config):
    local_path = _local_carbhistory_path(config)
    monitor_path = _monitor_carbhistory_path(config)
    local_records = _read_json_array(local_path)
    remote_records = _read_json_array(monitor_path)
    merged = merge_carbhistory_records(local_records, remote_records)
    _atomic_write_json(monitor_path, merged)
    return {
        "local_path": local_path,
        "monitor_path": monitor_path,
        "merged_count": len(merged),
        "local_count": len(local_records),
        "remote_count": len(remote_records),
    }


def read_carb_materialization_state(config):
    local_path = _local_carbhistory_path(config)
    monitor_path = _monitor_carbhistory_path(config)
    local_records = _read_json_array(local_path)
    monitor_records = _read_json_array(monitor_path)
    merged = merge_carbhistory_records(local_records, monitor_records)
    return {
        "local_carbhistory_path": local_path,
        "monitor_carbhistory_path": monitor_path,
        "local_carbs": local_records,
        "monitor_carbs": monitor_records,
        "merged_carbs_preview": merged[:20],
        "local_carbs_count": len(local_records),
        "monitor_carbs_count": len(monitor_records),
        "merged_carbs_count": len(merged),
    }
