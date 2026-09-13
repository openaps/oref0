from __future__ import print_function

import datetime
import json
import re


EVENT_SCHEMA = "openaps.local.event.v1"
ACK_SCHEMA = "openaps.local.event_ack.v1"
VALID_EVENT_TYPES = set(["carb_entry", "temp_target", "cancel_temp_target", "set_cgm_config", "bg_reading", "cgm_collector_control"])


class ValidationError(Exception):
    pass


def utc_now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def require_string(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError("%s must be a non-empty string" % key)
    return value


def validate_event(event):
    if not isinstance(event, dict):
        raise ValidationError("event must be an object")
    if event.get("schema") != EVENT_SCHEMA:
        raise ValidationError("unsupported schema")

    event_id = require_string(event, "event_id")
    patient_id = require_string(event, "patient_id")
    event_type = require_string(event, "event_type")
    require_string(event, "created_at")
    require_string(event, "effective_at")

    if event_type not in VALID_EVENT_TYPES:
        raise ValidationError("unsupported event_type %s" % event_type)

    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")

    if event_type == "carb_entry":
        carbs = payload.get("carbs_g")
        if not isinstance(carbs, int) or carbs < 1 or carbs > 300:
            raise ValidationError("carbs_g must be 1..300")
        absorption_minutes = payload.get("absorption_minutes")
        if absorption_minutes is not None and (not isinstance(absorption_minutes, int) or absorption_minutes < 30 or absorption_minutes > 600):
            raise ValidationError("absorption_minutes must be 30..600 or null")
        nightscout_event_type = payload.get("nightscout_event_type")
        if nightscout_event_type not in ("Carb Correction", "Meal Bolus"):
            raise ValidationError("nightscout_event_type must be Carb Correction or Meal Bolus")
        notes = payload.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValidationError("notes must be a string or null")
        if isinstance(notes, str) and len(notes) > 500:
            raise ValidationError("notes must be 500 characters or fewer")
    elif event_type == "temp_target":
        bottom = payload.get("target_bottom_mgdl")
        top = payload.get("target_top_mgdl")
        duration = payload.get("duration_minutes")
        if not isinstance(bottom, int) or bottom < 70 or bottom > 180:
            raise ValidationError("target_bottom_mgdl must be 70..180")
        if not isinstance(top, int) or top < 70 or top > 180:
            raise ValidationError("target_top_mgdl must be 70..180")
        if bottom > top:
            raise ValidationError("target_bottom_mgdl must be <= target_top_mgdl")
        if not isinstance(duration, int) or duration < 5 or duration > 480:
            raise ValidationError("duration_minutes must be 5..480")
    elif event_type == "bg_reading":
        sgv = payload.get("sgv")
        if not isinstance(sgv, int) or sgv < 20 or sgv > 600:
            raise ValidationError("sgv must be 20..600")
        direction = payload.get("direction")
        if direction is not None and not isinstance(direction, str):
            raise ValidationError("direction must be a string or null")
        trend = payload.get("trend")
        if trend is not None and not isinstance(trend, (int, float)):
            raise ValidationError("trend must be numeric or null")
        trend_rate = payload.get("trend_rate_mgdl_minute", payload.get("trend_rate_mgdl_min"))
        if trend_rate is not None and not isinstance(trend_rate, (int, float)):
            raise ValidationError("trend rate must be numeric or null")
        for key in ("source", "source_device_id", "collector_channel", "transmitter_id", "sensor_id"):
            value = payload.get(key)
            if value is not None and not isinstance(value, str):
                raise ValidationError("%s must be a string or null" % key)
        raw = payload.get("raw")
        if raw is not None and not isinstance(raw, dict):
            raise ValidationError("raw must be an object or null")
    elif event_type == "set_cgm_config":
        allowed_keys = set([
            "collector",
            "transmitter_id",
            "sensor_code",
            "alternate_bluetooth_channel",
            "apply_policy",
        ])
        if not set(payload.keys()).issubset(allowed_keys):
            raise ValidationError("set_cgm_config payload contains unsupported fields")
        collector = payload.get("collector")
        if collector is not None and collector not in ("logger", "xdripjs"):
            raise ValidationError("collector must be logger or xdripjs")
        transmitter_id = payload.get("transmitter_id")
        if transmitter_id is not None and (
            not isinstance(transmitter_id, str)
            or not re.match(r"^[A-Za-z0-9]{5,8}\Z", transmitter_id)
        ):
            raise ValidationError("transmitter_id must be a 5-8 character alphanumeric string or null")
        sensor_code = payload.get("sensor_code")
        if sensor_code is not None and (
            not isinstance(sensor_code, str)
            or not re.match(r"^[0-9]{4}\Z", sensor_code)
        ):
            raise ValidationError("sensor_code must be a 4-digit string or null")
        alternate = payload.get("alternate_bluetooth_channel")
        if alternate is not None and not isinstance(alternate, bool):
            raise ValidationError("alternate_bluetooth_channel must be a bool or null")
        apply_policy = payload.get("apply_policy")
        if apply_policy is not None and apply_policy not in (
            "active_collector_only",
            "next_collector_start",
            "all_rigs",
        ):
            raise ValidationError("apply_policy is invalid")
    elif event_type == "cgm_collector_control":
        allowed_keys = set([
            "collector",
            "desired_state",
            "transmitter_id",
            "alternate_bluetooth_channel",
            "election_id",
        ])
        if set(payload.keys()) != allowed_keys:
            raise ValidationError("cgm_collector_control payload must contain only collector control fields")
        if payload.get("collector") != "xdripjs":
            raise ValidationError("collector must be xdripjs")
        if payload.get("desired_state") not in ("running", "stopped", "status"):
            raise ValidationError("desired_state must be running, stopped, or status")
        transmitter_id = payload.get("transmitter_id")
        if not isinstance(transmitter_id, str) or not re.match(r"^[A-Za-z0-9]{6}\Z", transmitter_id):
            raise ValidationError("transmitter_id must be a 6-character alphanumeric string")
        if not isinstance(payload.get("alternate_bluetooth_channel"), bool):
            raise ValidationError("alternate_bluetooth_channel must be a bool")
        if not isinstance(payload.get("election_id"), str) or not payload.get("election_id"):
            raise ValidationError("election_id must be a non-empty string")

    return {
        "event_id": event_id,
        "patient_id": patient_id,
        "event_type": event_type,
        "json": json.dumps(event, sort_keys=True, separators=(",", ":")),
    }


def ack(event_id, patient_id, rig_id, status, details=None):
    return {
        "schema": ACK_SCHEMA,
        "event_id": event_id,
        "rig_id": rig_id,
        "patient_id": patient_id,
        "ack_status": status,
        "received_at": utc_now_iso(),
        "details": details or {},
    }
