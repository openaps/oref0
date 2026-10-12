import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openaps_locald.ble_server import Characteristic, RigInfoCharacteristic


class RigInfoReadTraceTests(unittest.TestCase):
    def setUp(self):
        # Replace only the platform DBus byte-array adapter on macOS.
        adapter = patch("openaps_locald.ble_server._bytes_to_dbus_array", side_effect=lambda data: data)
        adapter.start()
        self.addCleanup(adapter.stop)

    def harness(self, payload):
        return SimpleNamespace(
            uuid="synthetic-info-characteristic", bridge=SimpleNamespace(rig_info_read_trace=[]),
            _read_state_lock=lambda options: None, _read_value=lambda options: payload,
        )

    def test_chunk_trace_tracks_every_served_chunk_without_changing_payload(self):
        payload = b"A" * 900
        harness = self.harness(payload)
        harness._record_read_progress = lambda completed, total: RigInfoCharacteristic._record_read_progress(
            harness, completed, total)
        device = "synthetic-central"
        try:
            first = json.loads(bytes(Characteristic.ReadValue(harness, {"device": device})))
            frames = [first]
            for _ in range(first["total"] - 1):
                frames.append(json.loads(bytes(Characteristic.ReadValue(harness, {"device": device}))))
            self.assertEqual(b"".join(base64.b64decode(f["payload"]) for f in frames), payload)
            trace = harness.bridge.rig_info_read_trace
            self.assertEqual([r["completed_chunks"] for r in trace], list(range(1, first["total"] + 1)))
            self.assertTrue(all(r["expected_chunks"] == first["total"] for r in trace))
            self.assertTrue(all(set(r) == {"at_ms", "completed_chunks", "expected_chunks"} for r in trace))
        finally:
            Characteristic.clear_read_buffer(device)

    def test_raw_read_is_one_completed_chunk(self):
        harness = self.harness(b"synthetic-small")
        harness._record_read_progress = lambda completed, total: RigInfoCharacteristic._record_read_progress(
            harness, completed, total)
        self.assertEqual(bytes(Characteristic.ReadValue(harness, {})), b"synthetic-small")
        self.assertEqual(harness.bridge.rig_info_read_trace[-1]["completed_chunks"], 1)
        self.assertEqual(harness.bridge.rig_info_read_trace[-1]["expected_chunks"], 1)

    def test_trace_is_bounded_and_contains_no_payload_or_identifier(self):
        harness = self.harness(b"synthetic")
        for index in range(100):
            RigInfoCharacteristic._record_read_progress(harness, index + 1, 100)
        self.assertEqual(len(harness.bridge.rig_info_read_trace), 64)
        self.assertEqual(harness.bridge.rig_info_read_trace[0]["completed_chunks"], 37)
        self.assertNotIn("synthetic", json.dumps(harness.bridge.rig_info_read_trace))


if __name__ == "__main__":
    unittest.main()
