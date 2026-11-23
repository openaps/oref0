from __future__ import print_function

import json
import os
import sqlite3
import threading


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  materialization_status TEXT
);

CREATE TABLE IF NOT EXISTS acks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  ack_status TEXT NOT NULL,
  ack_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""


class EventDB(object):
    def __init__(self, path):
        self.path = path
        dirname = os.path.dirname(path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self):
        with self.lock:
            self.conn.close()

    def insert_event(self, validated):
        with self.lock:
            try:
                self.conn.execute(
                    "INSERT INTO events(event_id, patient_id, event_type, event_json) VALUES (?, ?, ?, ?)",
                    (validated["event_id"], validated["patient_id"], validated["event_type"], validated["json"]),
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def record_ack(self, ack):
        with self.lock:
            self.conn.execute(
                "INSERT INTO acks(event_id, ack_status, ack_json) VALUES (?, ?, ?)",
                (ack["event_id"], ack["ack_status"], json.dumps(ack, sort_keys=True)),
            )
            self.conn.commit()

    def update_materialization_status(self, event_id, materialization_status):
        with self.lock:
            self.conn.execute(
                "UPDATE events SET materialization_status = ? WHERE event_id = ?",
                (materialization_status, event_id),
            )
            self.conn.commit()

    def get_event(self, event_id):
        with self.lock:
            row = self.conn.execute("SELECT event_json FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            return None
        return json.loads(row["event_json"])

    def list_events(self, since=None, limit=100, event_type=None, descending=False):
        limit = max(1, min(int(limit), 500))
        with self.lock:
            if event_type is not None:
                rows = self.conn.execute("SELECT event_json FROM events").fetchall()
                events = [json.loads(row["event_json"]) for row in rows]
                events = [event for event in events if event.get("event_type") == event_type]
                if since:
                    events = [event for event in events if event.get("event_id") > since]
                events.sort(key=lambda event: event.get("event_id") or "", reverse=bool(descending))
                return events[:limit]
            if since:
                rows = self.conn.execute(
                    "SELECT event_json FROM events WHERE event_id > ? ORDER BY event_id %s LIMIT ?" % ("DESC" if descending else "ASC"),
                    (since, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT event_json FROM events ORDER BY event_id %s LIMIT ?" % ("DESC" if descending else "ASC"),
                    (limit,),
                ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]

    def list_acks(self, event_id):
        with self.lock:
            rows = self.conn.execute(
                "SELECT ack_json FROM acks WHERE event_id = ? ORDER BY id",
                (event_id,),
            ).fetchall()
        return [json.loads(row["ack_json"]) for row in rows]

    def get_event_and_acks(self, event_id):
        """Return one coherent observational snapshot without the delivery lock."""
        with self.lock:
            event_row = self.conn.execute(
                "SELECT event_json FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            ack_rows = self.conn.execute(
                "SELECT ack_json FROM acks WHERE event_id = ? ORDER BY id",
                (event_id,),
            ).fetchall()
        event = json.loads(event_row["event_json"]) if event_row is not None else None
        acks = [json.loads(row["ack_json"]) for row in ack_rows]
        return event, acks

    def counts(self):
        with self.lock:
            events = self.conn.execute("SELECT count(*) AS c FROM events").fetchone()["c"]
            acks = self.conn.execute("SELECT count(*) AS c FROM acks").fetchone()["c"]
        return {"events": events, "acks": acks}
