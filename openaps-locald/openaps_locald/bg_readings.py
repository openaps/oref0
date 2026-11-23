from __future__ import print_function

import json
from datetime import datetime

from .bg_history import bg_record_from_event
from .db import EventDB


BG_READINGS_SCHEMA = "openaps.local.bg_readings.v1"
BLE_SAFE_BYTES = 520
DEFAULT_BG_LIMIT = 3

_COMPACT_KEYS = [
    "date",
    "dateString",
    "sgv",
    "glucose",
    "direction",
    "trend_rate_mgdl_minute",
    "type",
    "device",
    "source",
    "source_device_id",
    "collector_channel",
    "transmitter_id",
    "openaps_app_event_id",
]


def _utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _json_len(payload):
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _compact_bg_record(event):
    record = bg_record_from_event(event)
    compact = {}
    for key in _COMPACT_KEYS:
        value = record.get(key)
        if value not in (None, ""):
            compact[key] = value
    event_id = event.get("event_id")
    if event_id:
        compact["event_id"] = event_id
        compact.setdefault("openaps_app_event_id", event_id)
    return compact


def _payload(config, records):
    return {
        "schema": BG_READINGS_SCHEMA,
        "rig_id": config.get("rig_id"),
        "patient_id": config.get("patient_id"),
        "generated_at": _utc_now(),
        "bg_readings": records,
    }


def _fit_for_ble(config, records):
    for count in range(len(records), -1, -1):
        payload = _payload(config, records[:count])
        if _json_len(payload) <= BLE_SAFE_BYTES:
            return payload
    # Empty payload metadata should fit, but keep a safe fallback for unusual ids.
    return {"schema": BG_READINGS_SCHEMA, "bg_readings": []}


def read_bg_readings_payload(config, limit=DEFAULT_BG_LIMIT):
    limit = max(1, min(int(limit), 20))
    db = EventDB(config["db_path"])
    try:
        events = db.list_events(limit=limit, event_type="bg_reading", descending=True)
    finally:
        db.close()
    records = [_compact_bg_record(event) for event in events]
    return _fit_for_ble(config, records)
