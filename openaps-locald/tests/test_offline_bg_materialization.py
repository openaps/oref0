import json
import tempfile
import unittest

from openaps_locald.install_config import build_install_config
from openaps_locald.materialize import materialize_event


class OfflineBGMaterializationTests(unittest.TestCase):
    def test_install_defaults_put_ble_bg_into_pump_loop_glucose(self):
        with tempfile.TemporaryDirectory(prefix="offline-bg-test-") as directory:
            config = build_install_config({}, directory, "127.0.0.1", 8787)
            self.assertTrue(config["materialize_bg_readings"])
            self.assertTrue(config["merge_local_bg_into_monitor"])
            event = {
                "schema": "openaps.local.event.v1",
                "event_id": "synthetic-bg-event",
                "patient_id": "patient-placeholder",
                "event_type": "bg_reading",
                "created_at": "2026-01-01T00:05:00Z",
                "effective_at": "2026-01-01T00:05:00Z",
                "payload": {"sgv": 101, "source": "phone-placeholder"},
            }
            result = materialize_event(event, config)
            self.assertEqual(result, "materialized_into_monitor_glucose")
            for path in (config["local_glucose_path"], config["monitor_glucose_path"]):
                with open(path) as stream:
                    records = json.load(stream)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["dateString"], event["effective_at"])
                self.assertEqual(records[0]["openapsAppEventId"], event["event_id"])


if __name__ == "__main__":
    unittest.main()
