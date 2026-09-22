from __future__ import print_function

import json
import os
import socket
import time
try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen

from . import __version__
from .pump_history import read_pumphistory_summary
from .collector_control import read_collector_status
from .xdripjs_config import read_xdripjs_config_state


def file_age_seconds(path):
    try:
        return int(time.time() - os.path.getmtime(path))
    except OSError:
        return None


def read_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def bg_status(myopenaps):
    path = os.path.join(myopenaps, "monitor", "glucose.json")
    age = file_age_seconds(path)
    data = read_json(path)
    entry = None
    if isinstance(data, list) and data:
        entry = data[0]
    elif isinstance(data, dict):
        entry = data
    else:
        entry = {}
    sgv = entry.get("sgv", entry.get("glucose")) if isinstance(entry, dict) else None
    source = _first_non_empty(entry.get("source"), entry.get("device"), entry.get("type")) if isinstance(entry, dict) else None
    return {
        "sgv": sgv,
        "source": source,
        "age_seconds": age,
        "fresh": age is not None and age <= 600,
    }


def loop_status():
    completed_age = file_age_seconds("/tmp/pump_loop_completed")
    success_age = file_age_seconds("/tmp/pump_loop_success")
    enacted_age = file_age_seconds("/tmp/pump_loop_enacted")
    if completed_age is not None and completed_age <= 600:
        state = "completed_recently"
    elif enacted_age is not None and completed_age is not None and enacted_age < completed_age:
        state = "running"
    elif completed_age is not None:
        state = "stale"
    else:
        state = "unknown"
    return {
        "state": state,
        "completed_age_seconds": completed_age,
        "success_age_seconds": success_age,
        "enacted_age_seconds": enacted_age,
    }


def nightscout_status(config):
    host = config.get("nightscout_host")
    result = {
        "configured": bool(host),
        "host": host,
        "reachable": None,
        "status": None,
    }
    if not host:
        return result
    try:
        response = urlopen(host.rstrip("/") + "/api/v1/status.json", timeout=2)
        payload = json.loads(response.read().decode("utf-8"))
        result["reachable"] = True
        result["status"] = payload.get("status")
        result["version"] = payload.get("version")
    except Exception as e:
        result["reachable"] = False
        result["error"] = str(e)
    return result


def status(config, db):
    myopenaps = config["myopenaps_dir"]
    counts = db.counts()
    xdripjs_state = read_xdripjs_config_state(config)
    collector_state = read_collector_status(config)
    pumphistory_state = read_pumphistory_summary(config)
    return {
        "schema": "openaps.local.status.v1",
        "version": __version__,
        "rig_id": config["rig_id"],
        "hostname": socket.gethostname(),
        "patient_id": config["patient_id"],
        "myopenaps_dir": myopenaps,
        "nightscout_host": config.get("nightscout_host"),
        "event_count": counts["events"],
        "ack_count": counts["acks"],
        "materialize_temp_targets": bool(config.get("materialize_temp_targets")),
        "materialize_carbs": bool(config.get("materialize_carbs")),
        "materialize_bg_readings": bool(config.get("materialize_bg_readings")),
        "merge_local_bg_into_monitor": bool(config.get("merge_local_bg_into_monitor")),
        "xdripjs_enabled": bool(config.get("xdripjs_enabled")),
        "files": {
            "glucose_age_seconds": file_age_seconds(os.path.join(myopenaps, "monitor", "glucose.json")),
            "local_glucose_age_seconds": file_age_seconds(os.path.join(myopenaps, "monitor", "local-glucose.json")),
            "meal_age_seconds": file_age_seconds(os.path.join(myopenaps, "monitor", "meal.json")),
            "profile_age_seconds": file_age_seconds(os.path.join(myopenaps, "settings", "profile.json")),
        },
        "loop": loop_status(),
        "bg": bg_status(myopenaps),
        "pump_history": pumphistory_state,
        "xdripjs": xdripjs_state,
        "collector": collector_state,
        "connectivity": {
            "nightscout": nightscout_status(config),
        },
        "event_log": {
            "event_count": counts["events"],
            "ack_count": counts["acks"],
        },
    }
