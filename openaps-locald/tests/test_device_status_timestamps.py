import json
import os
import shutil
import tempfile
import unittest

from openaps_locald.device_status import read_device_status_payload


class DeviceStatusTimestampTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        os.mkdir(os.path.join(self.root, "enact"))
        os.mkdir(os.path.join(self.root, "monitor"))
        self.config = {"myopenaps_dir": self.root, "rig_id": "synthetic-rig"}
        self.epoch = 946684800
        self.timestamp = "2000-01-01T00:00:00Z"

    def write(self, name, payload):
        path = os.path.join(self.root, "enact", name + ".json")
        with open(path, "w") as handle:
            json.dump(payload, handle)
        os.utime(path, (self.epoch, self.epoch))

    def status(self):
        return read_device_status_payload(self.config)["device_statuses"][0]

    def test_explicit_timestamp_is_preserved(self):
        self.write("enacted", {"timestamp": self.timestamp, "predBGs": {"IOB": [100]}})
        self.assertEqual(self.status()["openaps"]["enacted"]["timestamp"], self.timestamp)

    def test_undated_records_use_source_time(self):
        for name in ("suggested", "enacted"):
            self.write(name, {"predBGs": {"IOB": [100]}})
        status = self.status()
        self.assertNotEqual(status["created_at"], self.timestamp)
        for name in ("suggested", "enacted"):
            self.assertEqual(status["openaps"][name]["timestamp"], self.timestamp)

    def test_repeated_responses_do_not_refresh_source_time(self):
        self.write("enacted", {"predBGs": {"IOB": [100]}})
        self.assertEqual(self.status()["openaps"]["enacted"]["timestamp"], self.timestamp)
        self.assertEqual(self.status()["openaps"]["enacted"]["timestamp"], self.timestamp)

    def test_mills_is_preserved_without_inventing_timestamp(self):
        self.write("enacted", {"mills": self.epoch * 1000, "predBGs": {"IOB": [100]}})
        record = self.status()["openaps"]["enacted"]
        self.assertEqual(record["mills"], self.epoch * 1000)
        self.assertNotIn("timestamp", record)

    def test_missing_and_invalid_files_do_not_create_evidence(self):
        with open(os.path.join(self.root, "enact", "enacted.json"), "w") as handle:
            handle.write("invalid json")
        self.assertNotIn("enacted", self.status().get("openaps", {}))
        self.assertNotIn("suggested", self.status().get("openaps", {}))

    def test_no_temp_required_reason_is_preserved(self):
        self.write("suggested", {"reason": "No Temp Required", "predBGs": {"IOB": [100]}})
        self.assertEqual(self.status()["openaps"]["suggested"]["reason"], "No Temp Required")

    def test_ble_compaction_preserves_source_time(self):
        self.write("suggested", {"predBGs": {"IOB": list(range(48)), "COB": list(range(48))}})
        self.config["ble_device_status_safe_bytes"] = 300
        self.assertEqual(self.status()["openaps"]["suggested"]["timestamp"], self.timestamp)
