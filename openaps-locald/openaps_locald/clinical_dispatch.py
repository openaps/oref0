"""Shared serialized clinical event path for legacy and authenticated transports.

Authentication must be checked by the owner; a request field is never authority.
No TLS/HTTP/BLE framing belongs here. Reuse one dispatcher per service database.
"""
from __future__ import print_function

import json
import base64
import zlib
import threading
from urllib.parse import unquote

from .config import accepted_patient_ids
from .models import ValidationError, ack, validate_event
from .wifi import WiFiService, WiFiError


MAINTENANCE_SCHEMA = "openaps.local.maintenance.v1"
# The authenticated TLS response frame is 65,532 bytes including its own
# envelope. Leave room for that envelope and reject an oversized full history
# rather than silently removing pump events from a clinical read.
MAX_MAINTENANCE_BODY_BYTES = 60 * 1024


class ClinicalEventDispatcher(object):
    def __init__(self, config, db, materialize, collector_details, log, event_summary):
        self.config, self.db = config, db
        self.materialize, self.collector_details = materialize, collector_details
        self.log, self.event_summary = log, event_summary
        self.lock = threading.RLock()

    def process_legacy(self, events, log_prefix="POST /v1/events"):
        with self.lock:
            return self._process_events(events, log_prefix)

    def process_authenticated(self, events, authorize, log_prefix="authenticated events"):
        # The callable is a transport-owned live trust/destination check, not a
        # client-controlled Boolean or a bearer passed through a loopback URL.
        if not callable(authorize):
            raise ValueError("live authorization callback required")
        with self.lock:
            result = []
            for event in events:
                authorize()
                result.extend(self._process_events([event], log_prefix))
            return result

    def _process_events(self, events, log_prefix="POST /v1/events"):
        config, db = self.config, self.db
        _api_log, _event_summary = self.log, self.event_summary
        materialize_event_result, collector_ack_details = self.materialize, self.collector_details
        _api_log("%s batch_size=%d" % (log_prefix, len(events)))
        acks = []
        for index, event in enumerate(events):
            event_id = event.get("event_id") if isinstance(event, dict) else None
            patient_id = event.get("patient_id") if isinstance(event, dict) else None
            _api_log("%s item=%d %s" % (log_prefix, index, _event_summary(event)))
            try:
                validated = validate_event(event)
                event_id = validated["event_id"]
                patient_id = validated["patient_id"]
                if patient_id not in accepted_patient_ids(config):
                    event_ack = ack(event_id, patient_id, config["rig_id"], "rejected_wrong_patient")
                    _api_log(
                        "%s item=%d event_id=%s outcome=rejected_wrong_patient request_patient_id=%s rig_patient_id=%s"
                        % (log_prefix, index, event_id, patient_id, config["patient_id"])
                    )
                else:
                    inserted = db.insert_event(validated)
                    materialization_result = materialize_event_result(event, config) if inserted else {"materialization": "duplicate"}
                    if not inserted:
                        materialization_result.update(collector_ack_details(event, config))
                    materialized = materialization_result["materialization"]
                    if inserted:
                        db.update_materialization_status(event_id, materialized)
                    _api_log(
                        "%s item=%d event_id=%s outcome=%s materialization=%s"
                        % (log_prefix, index, event_id, "stored" if inserted else "duplicate", materialized)
                    )
                    ack_details = {
                        "duplicate": not inserted,
                        "materialization": materialized,
                    }
                    for key in (
                        "desired_state",
                        "actual_state",
                        "transmitter_id",
                        "alternate_bluetooth_channel",
                        "election_id",
                        "cron_enabled",
                        "process_count",
                    ):
                        if key in materialization_result:
                            ack_details[key] = materialization_result[key]
                    event_ack = ack(
                        event_id,
                        patient_id,
                        config["rig_id"],
                        "stored" if inserted else "duplicate",
                        ack_details,
                    )
            except ValidationError as exc:
                _api_log(
                    "%s item=%d %s outcome=rejected_invalid_schema error=%s"
                    % (log_prefix, index, _event_summary(event), exc)
                )
                event_ack = ack(event_id or "unknown", patient_id or config["patient_id"], config["rig_id"], "rejected_invalid_schema", {"error": str(exc)})
            except Exception as exc:
                _api_log(
                    "%s item=%d %s outcome=error_materialization_failed error=%s"
                    % (log_prefix, index, _event_summary(event), exc)
                )
                event_ack = ack(event_id or "unknown", patient_id or config["patient_id"], config["rig_id"], "error_materialization_failed", {"error": str(exc)})
            db.record_ack(event_ack)
            acks.append(event_ack)
        return acks


class ClinicalReadDispatcher(object):
    def __init__(self, config, db, providers, lock):
        self.config, self.db, self.providers, self.lock = config, db, providers, lock
        self.wifi = WiFiService(config)

    def wifi_authenticated(self, method, path, body, authorize):
        if not callable(authorize):
            raise ValueError("live authorization callback required")
        try:
            return self.wifi.request(method, path, body, authorize)
        except WiFiError as exc:
            return exc.status, {"error": exc.code}

    def read_legacy(self, path, query):
        with self.lock:
            return self._read(path, query)

    def read_authenticated(self, path, query, authorize):
        if not callable(authorize):
            raise ValueError("live authorization callback required")
        with self.lock:
            authorize()
            response = self._read(path, query)
            # A slow file/database read must not release data after trust changes.
            authorize()
            return response

    def _read(self, path, query):
        config, db = self.config, self.db
        if path == "/v1/health":
            return (200, {"ok": True, "rig_id": config["rig_id"]})
        elif path == "/v1/rig":
            return (200, {
                "schema": "openaps.local.rig.v1",
                "rig_id": config["rig_id"],
                "patient_id": config["patient_id"],
                "protocol_version": 1,
                "capabilities": [
                    "events.store",
                    "events.http",
                    "bg.readings",
                    "bg.materialize",
                    "cgm.config",
                    "cgm_collector_control",
                    "pump_history_read",
                    "device_status_read",
                ],
                "authorization": self.providers["metadata"](),
            })
        elif path == "/v1/status":
            status_payload = self.providers["status"](config, db)
            status_payload["authorization"] = self.providers["diagnostics"]()
            return (200, status_payload)
        elif path in ("/v1/device-status", "/v1/devicestatus"):
            return (200, self.providers["device_status"](config))
        elif path == "/v1/maintenance":
            allowed = frozenset(("include_pump_history", "include_device_status",
                                 "include_bg_readings", "limit", "encoding"))
            if set(query) - allowed:
                return (400, {"error": "invalid_maintenance_query"})
            encoding = query.get("encoding", ["identity"])
            if encoding not in (["identity"], ["deflate-raw-v1"]):
                return (400, {"error": "invalid_maintenance_query"})
            include = {}
            for name in ("pump_history", "device_status", "bg_readings"):
                raw = query.get("include_" + name, ["1"])
                if len(raw) != 1 or raw[0] not in ("0", "1"):
                    return (400, {"error": "invalid_maintenance_query"})
                include[name] = raw[0] == "1"
            raw_limit = query.get("limit", ["64"])
            if len(raw_limit) != 1 or not raw_limit[0].isdigit() or len(raw_limit[0]) > 2:
                return (400, {"error": "invalid_maintenance_query"})
            limit = int(raw_limit[0])
            if not 1 <= limit <= 64 or not any(include.values()):
                return (400, {"error": "invalid_maintenance_query"})

            payload = {
                "schema": MAINTENANCE_SCHEMA,
                "rig_id": config["rig_id"],
                "patient_id": config["patient_id"],
            }
            if include["pump_history"]:
                history = self.providers["pump_history"](config, limit=limit)
                if not isinstance(history, dict) or history.get("rig_id") != config["rig_id"] or \
                        history.get("patient_id") != config["patient_id"]:
                    return (503, {"error": "maintenance_source_identity"})
                payload["pump_history"] = history
            if include["device_status"]:
                device_status = self.providers["device_status"](config)
                if not isinstance(device_status, dict) or not isinstance(device_status.get("device_statuses"), list):
                    return (503, {"error": "maintenance_source_invalid"})
                if (device_status.get("rig_id", config["rig_id"]) != config["rig_id"] or
                        device_status.get("patient_id", config["patient_id"]) != config["patient_id"]):
                    return (503, {"error": "maintenance_source_identity"})
                device_status = dict(device_status)
                device_status["rig_id"] = config["rig_id"]
                device_status["patient_id"] = config["patient_id"]
                payload["device_status"] = device_status
            if include["bg_readings"]:
                bg_readings = self.providers["bg_readings"](config)
                if not isinstance(bg_readings, dict) or bg_readings.get("rig_id") != config["rig_id"] or \
                        bg_readings.get("patient_id") != config["patient_id"]:
                    return (503, {"error": "maintenance_source_identity"})
                payload["bg_readings"] = bg_readings
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(encoded) > MAX_MAINTENANCE_BODY_BYTES:
                return (413, {"error": "maintenance_too_large"})
            if encoding == ["deflate-raw-v1"]:
                compressor = zlib.compressobj(5, zlib.DEFLATED, -15)
                compressed = compressor.compress(encoded) + compressor.flush()
                envelope = {"schema": "openaps.local.maintenance.deflate.v1",
                            "rig_id": config["rig_id"], "patient_id": config["patient_id"],
                            "uncompressed_bytes": len(encoded),
                            "payload": base64.b64encode(compressed).decode("ascii")}
                if len(json.dumps(envelope, separators=(",", ":")).encode("utf-8")) < len(encoded):
                    return (200, envelope)
            return (200, payload)
        elif path == "/v1/materialization":
            return (200, {
                "schema": "openaps.local.materialization.v1",
                "rig_id": config["rig_id"],
                "patient_id": config["patient_id"],
                "materialize_temp_targets": bool(config.get("materialize_temp_targets")),
                "materialize_carbs": bool(config.get("materialize_carbs")),
                "merge_local_carbs_into_monitor": bool(config.get("merge_local_carbs_into_monitor")),
                "materialize_bg_readings": bool(config.get("materialize_bg_readings")),
                "merge_local_bg_into_monitor": bool(config.get("merge_local_bg_into_monitor")),
                "state": self.providers["materialization"](config),
            })
        elif path == "/v1/events":
            since = query.get("since", [None])[0]
            limit = query.get("limit", [100])[0]
            return (200, {"events": db.list_events(since=since, limit=limit)})
        elif path == "/v1/bg-readings":
            limit = query.get("limit", [100])[0]
            since = query.get("since", [None])[0]
            events = db.list_events(since=since, limit=500, event_type="bg_reading", descending=True)
            return (200, {"bg_readings": events[: max(1, min(int(limit), 500))]})
        elif path == "/v1/bg-readings/latest":
            events = db.list_events(limit=500, event_type="bg_reading", descending=True)
            bg_event = self.providers["latest_bg"](events)
            if bg_event is None:
                return (404, {"error": "not_found"})
            else:
                return (200, {"bg_reading": bg_event})
        elif path in ("/v1/pumphistory", "/v1/pump-history"):
            return (200, self.providers["pump_history"](config, limit=self.providers["query_limit"](query, 288)))
        elif path.startswith("/v1/events/") and path.endswith("/acks"):
            event_id = unquote(path.split("/")[3])
            return (200, {"acks": db.list_acks(event_id)})
        elif path.startswith("/v1/events/"):
            event_id = unquote(path.split("/")[3])
            event = db.get_event(event_id)
            if event is None:
                return (404, {"error": "not_found"})
            else:
                return (200, event)
        else:
            return (404, {"error": "not_found"})
