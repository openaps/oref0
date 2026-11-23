from __future__ import print_function

from .db import EventDB
from .materialize import materialize_event
from .xdripjs_config import read_xdripjs_config_state


def replay_latest_set_cgm_config(config):
    db = EventDB(config["db_path"])
    try:
        events = db.list_events(event_type="set_cgm_config", descending=True, limit=1)
        if not events:
            return {
                "status": "no_set_cgm_config",
                "event_id": None,
                "materialization": None,
            }
        event = events[0]
        before = read_xdripjs_config_state(config)
        materialization = materialize_event(event, config)
        db.update_materialization_status(event.get("event_id"), materialization)
        after = read_xdripjs_config_state(config)
        return {
            "status": "replayed",
            "event_id": event.get("event_id"),
            "materialization": materialization,
            "before": before,
            "after": after,
        }
    finally:
        db.close()
