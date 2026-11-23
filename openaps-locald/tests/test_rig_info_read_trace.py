import base64
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from openaps_locald.ble_server import Characteristic, RigInfoCharacteristic
from openaps_locald.ble_server import _ATT_CHUNK, _read_envelopes_for_payload


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

    def test_compact_id_preserves_all_uuid_bits_and_reduces_round_trips(self):
        identity = uuid.UUID("11111111-2222-4333-8444-555555555555")
        with patch("openaps_locald.ble_server.uuid.uuid4", return_value=identity):
            frames = _read_envelopes_for_payload(b"A" * 864, "synthetic-info")
        first = json.loads(frames[0])
        token = first["message_id"].split("-", 1)[1]
        self.assertEqual(base64.urlsafe_b64decode(token + "=="), identity.bytes)
        self.assertEqual(len(token), 22)
        self.assertEqual(len(frames), 21)  # Previously 24 reads at 36 bytes.

    def test_all_envelopes_fit_att_and_reassemble_at_digit_boundaries(self):
        for size in [185, 864, 4096, 65536]:
            with self.subTest(size=size):
                payload = b"A" * size
                frames = _read_envelopes_for_payload(payload, "synthetic-info")
                decoded = [json.loads(frame) for frame in frames]
                self.assertTrue(all(len(frame) <= _ATT_CHUNK for frame in frames))
                self.assertEqual([f["seq"] for f in decoded], list(range(len(frames))))
                self.assertTrue(all(f["total"] == len(frames) for f in decoded))
                self.assertEqual(b"".join(base64.b64decode(f["payload"]) for f in decoded), payload)


if __name__ == "__main__":
    unittest.main()
