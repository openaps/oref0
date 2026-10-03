import json
import os
import shutil
import tempfile
import unittest

from openaps_locald.bg_history import merge_bg_records, merge_local_bg_into_monitor, write_local_bg_record


class BGHistoryOrderingTests(unittest.TestCase):
    def test_newer_monitor_record_precedes_local_backlog(self):
        older = {"date": 1000, "event_id": "synthetic-old"}
        newer = {"date": 2000, "event_id": "synthetic-new"}
        self.assertEqual(merge_bg_records([older], [newer]), [newer, older])

    def test_timestamp_fallback_and_missing_timestamp(self):
        missing = {"dateString": "invalid"}
        epoch = {"dateString": "1970-01-01T00:00:00Z"}
        newer = {"date": "1000"}
        self.assertEqual(merge_bg_records([missing, epoch], [newer]), [newer, epoch, missing])

    def test_duplicate_precedence_and_equal_time_are_preserved(self):
        local = {"date": 1000, "event_id": "synthetic-same", "source": "local"}
        duplicate = dict(local, source="monitor")
        other = {"date": 1000, "event_id": "synthetic-other"}
        self.assertEqual(merge_bg_records([local], [duplicate, other]), [local, other])

    def test_older_arrival_does_not_replace_current_local_or_monitor_bg(self):
        directory = tempfile.mkdtemp()
        try:
            config = {"myopenaps_dir": directory}
            for minute in (10, 5):
                write_local_bg_record({"event_id": "synthetic-%s" % minute,
                                       "effective_at": "2000-01-01T00:%02d:00Z" % minute,
                                       "payload": {"sgv": 100}}, config)
            merge_local_bg_into_monitor(config)
            for name in ("local-glucose.json", "glucose.json"):
                with open(os.path.join(directory, "monitor", name)) as handle:
                    records = json.load(handle)
                self.assertEqual([r["openaps_app_event_id"] for r in records],
                                 ["synthetic-10", "synthetic-5"])
        finally:
            shutil.rmtree(directory)
