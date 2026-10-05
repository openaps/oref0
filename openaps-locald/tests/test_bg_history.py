import json
import os
import shutil
import tempfile
import unittest

from openaps_locald.bg_history import _atomic_write_json, merge_bg_records, merge_local_bg_into_monitor, write_local_bg_record


class BGHistoryOrderingTests(unittest.TestCase):
    def test_large_cache_compact_write_preserves_every_record(self):
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, "glucose.json")
            records = [{"date": index, "sgv": 100,
                        "event_id": "synthetic-%s" % index,
                        "notes": "synthetic unicode \u2603", "noise": None}
                       for index in range(5000)]
            _atomic_write_json(path, records)
            with open(path) as handle:
                encoded = handle.read()
            self.assertEqual(json.loads(encoded), records)
            self.assertEqual(encoded.count("\n"), 1)
            self.assertEqual(os.listdir(directory), ["glucose.json"])
        finally:
            shutil.rmtree(directory)

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

    def test_skipped_duplicate_does_not_add_new_identity_aliases(self):
        first = {"date": 1000, "event_id": "synthetic-first"}
        duplicate = dict(first, reading_id="synthetic-new-alias")
        distinct = {"date": 2000, "reading_id": "synthetic-new-alias"}
        self.assertEqual(merge_bg_records([first], [duplicate, distinct]),
                         [distinct, first])

    def test_fallback_identity_and_string_coercion_are_preserved(self):
        first = {"date": 1000, "glucose": 100, "device": "synthetic"}
        duplicate = {"date": "1000", "sgv": "100", "device": "synthetic"}
        self.assertEqual(merge_bg_records([first], [duplicate]), [first])

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
