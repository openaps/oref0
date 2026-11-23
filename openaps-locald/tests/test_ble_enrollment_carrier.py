import json
import os
import tempfile
import threading
import time
import unittest
import uuid

from openaps_locald.ble_protocol import (
    BleProtocolError,
    ENROLLMENT_RESULT_SCHEMA,
)
from openaps_locald.ble_server import RigBridge
from openaps_locald.ble_server import BLE_ENROLLMENT_CARRIER_LIFETIME_SECONDS
from openaps_locald.http_api import ThreadedHTTPServer, make_handler
from openaps_locald.reverse_enrollment import ReverseEnrollmentWorkflow


def challenge():
    return {
        "schema": "openaps.ns-write-challenge.v1",
        "authority_context_id": "ns_" + "a" * 64,
        "verifier_credential_id": "b" * 64,
        "verifier_device_kind": "phone",
        "peer_credential_id": "c" * 64,
        "peer_device_kind": "rig",
        "nonce": "d" * 64,
    }


class Runtime(object):
    mode = "legacy"
    identity = None
    credential_id = None
    client = None
    carrier_ready_cached = False
    last_state = {"classification": "legacy"}

    @staticmethod
    def start_periodic_reconciliation():
        return None


class FakeReverseWorkflow(ReverseEnrollmentWorkflow):
    def __init__(self, result):
        self.result = result
        self.calls = []

    def handle(self, body, started_at=None):
        self.calls.append((body, started_at))
        return self.result


class BLEEnrollmentCarrierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ble-enrollment-carrier-")
        self.server = None
        self.worker = None
        self.handler = None

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.worker.join(2)
            self.handler.db.close()
        self.directory.cleanup()

    def start_http(self, publisher=None, workflow=None):
        self.handler = make_handler({
            "db_path": os.path.join(self.directory.name, "events.sqlite3"),
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "auth_token": "synthetic-token",
        }, enrollment_challenge_publisher=publisher,
           enrollment_reverse_workflow=workflow,
           enrollment_clock=time.monotonic)
        self.server = ThreadedHTTPServer(("127.0.0.1", 0), self.handler)
        self.worker = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.02))
        self.worker.daemon = True
        self.worker.start()
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def bridge(self, base_url="http://127.0.0.1:8787", monotonic=None):
        return RigBridge({
            "rig_id": "rig-placeholder",
            "patient_id": "patient-placeholder",
            "myopenaps_dir": self.directory.name,
            "ble_http_base_url": base_url,
        }, authorization_runtime=Runtime(), monotonic=monotonic)

    @staticmethod
    def carrier(route, payload, request_id=None, request_override=None):
        request_id = request_id or str(uuid.uuid4())
        request = request_override or {
            "schema": "openaps.ble.enrollment-carrier.v1",
            "request_id": request_id,
            "route": route,
            "payload": payload,
        }
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 1024:
            raise AssertionError("fixture must fit one BLE chunk")
        return request_id, json.dumps({
            "envelope_version": 1,
            "message_id": request_id,
            "seq": 0,
            "total": 1,
            "encoding": "utf8",
            "payload": encoded.decode("utf-8"),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def test_challenge_and_reverse_reuse_existing_http_endpoints(self):
        published = []
        challenge_url = self.start_http(publisher=lambda value: published.append(value))
        bridge = self.bridge(challenge_url)
        bridge.post_event = lambda _event: self.fail("carrier reached clinical event dispatch")

        challenge_id, challenge_frame = self.carrier("challenge", challenge())
        challenge_ack = bridge.submit_ble_write(challenge_frame, "connection-a")
        self.assertEqual(challenge_ack, {
            "schema": ENROLLMENT_RESULT_SCHEMA,
            "request_id": challenge_id,
            "status": 202,
            "body": None,
        })
        self.assertEqual(published, [challenge()])

        # The same HTTP route owns reverse proof orchestration and its bounded
        # status/body semantics; the BLE bridge only transports the result.
        workflow = FakeReverseWorkflow((200, {
            "schema": "openaps.ns-reverse-challenge.v1",
            "challenge": challenge(),
        }))
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)
        self.handler.db.close()
        self.server = None
        self.worker = None
        self.handler = None
        reverse_url = self.start_http(workflow=workflow)
        reverse_bridge = self.bridge(reverse_url)

        class Notifier(object):
            def __init__(self):
                self.values = []

            def _set_value(self, value):
                self.values.append(value)

        notifier = Notifier()
        reverse_bridge.ack_characteristic = notifier
        reverse_bridge.post_event = lambda _event: self.fail(
            "reverse carrier reached clinical event dispatch")
        reverse_payload = {
            "schema": "openaps.ns-reverse-begin.v1",
            "challenge": challenge(),
            "phone_public_key_der": "A" * 124,
        }
        reverse_id, reverse_frame = self.carrier("reverse", reverse_payload)
        reverse_ack = reverse_bridge.submit_ble_write(reverse_frame, "connection-b")
        self.assertEqual(reverse_ack, {
            "schema": ENROLLMENT_RESULT_SCHEMA,
            "request_id": reverse_id,
            "status": 200,
            "body": workflow.result[1],
        })
        self.assertEqual(len(workflow.calls), 1)
        self.assertEqual(notifier.values, [])
        self.assertEqual(reverse_bridge.ack_for_connection("connection-b"), reverse_ack)
        self.assertEqual(reverse_bridge.last_ack["ack_status"], "idle")

    def test_http_errors_are_bounded_ack_statuses_without_body(self):
        url = self.start_http()  # Missing endpoint provider intentionally returns 503.
        bridge = self.bridge(url)
        request_id, frame = self.carrier("challenge", challenge())
        ack = bridge.submit_ble_write(frame, "connection-a")
        self.assertEqual(ack, {
            "schema": ENROLLMENT_RESULT_SCHEMA,
            "request_id": request_id,
            "status": 503,
            "body": None,
        })

        bridge = self.bridge()
        for status in (400, 425, 429, 503):
            bridge._post_enrollment_carrier = lambda _route, _payload, code=status: (code, None)
            request_id, frame = self.carrier("reverse", {
                "schema": "openaps.ns-reverse-ready.v1",
                "nonce": "e" * 64,
            })
            ack = bridge.submit_ble_write(frame, "connection-%d" % status)
            self.assertEqual(ack, {
                "schema": ENROLLMENT_RESULT_SCHEMA,
                "request_id": request_id,
                "status": status,
                "body": None,
            })

    def test_existing_challenge_and_reverse_validation_errors_are_carried(self):
        published = []
        url = self.start_http(
            publisher=lambda value: published.append(value),
            workflow=ReverseEnrollmentWorkflow(None, None, None, None, clock=time.monotonic))
        bridge = self.bridge(url)

        invalid_challenge = dict(challenge())
        invalid_challenge["peer_device_kind"] = "phone"
        request_id, frame = self.carrier("challenge", invalid_challenge)
        self.assertEqual(bridge.submit_ble_write(frame, "connection-challenge-error"), {
            "schema": ENROLLMENT_RESULT_SCHEMA,
            "request_id": request_id,
            "status": 400,
            "body": None,
        })

        request_id, frame = self.carrier("reverse", {"schema": "unsupported"})
        self.assertEqual(bridge.submit_ble_write(frame, "connection-reverse-error"), {
            "schema": ENROLLMENT_RESULT_SCHEMA,
            "request_id": request_id,
            "status": 400,
            "body": None,
        })
        self.assertEqual(published, [])

    def test_malformed_route_payload_identity_and_reserved_version_never_dispatch(self):
        bridge = self.bridge()
        bridge.post_event = lambda _event: self.fail("malformed carrier reached clinical dispatch")
        valid_id = str(uuid.uuid4())
        malformed = [
            ({"schema": "openaps.ble.enrollment-carrier.v1", "request_id": valid_id,
              "route": "other", "payload": {}}, valid_id),
            ({"schema": "openaps.ble.enrollment-carrier.v1", "request_id": valid_id,
              "route": "challenge", "payload": []}, valid_id),
            ({"schema": "openaps.ble.enrollment-carrier.v1", "request_id": valid_id,
              "route": "challenge", "payload": {"nested": {"a": {"b": "deep"}}}}, valid_id),
            ({"schema": "openaps.ble.enrollment-carrier.v0", "request_id": valid_id,
              "route": "challenge", "payload": {}}, valid_id),
        ]
        for request, message_id in malformed:
            _request_id, frame = self.carrier(
                request.get("route", "challenge"), request.get("payload", {}),
                request_id=message_id, request_override=request)
            with self.assertRaises(BleProtocolError):
                bridge.submit_ble_write(frame, "connection-a")

        request_id, frame = self.carrier("challenge", challenge())
        other_id = str(uuid.uuid4())
        envelope = json.loads(frame.decode("utf-8"))
        envelope["message_id"] = other_id
        with self.assertRaises(BleProtocolError):
            bridge.submit_ble_write(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                "connection-a")

        uppercase_id = request_id.upper()
        _id, frame = self.carrier("challenge", challenge(), request_id=uppercase_id)
        with self.assertRaises(BleProtocolError):
            bridge.submit_ble_write(frame, "connection-a")

        duplicate_fields = (
            '{"schema":"openaps.ble.enrollment-carrier.v1",'
            '"request_id":"%s","route":"challenge","route":"reverse",'
            '"payload":{}}' % valid_id
        ).encode("ascii")
        envelope = {
            "envelope_version": 1, "message_id": valid_id, "seq": 0,
            "total": 1, "encoding": "utf8", "payload": duplicate_fields.decode("ascii"),
        }
        with self.assertRaises(BleProtocolError):
            bridge.submit_ble_write(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                "connection-a")

    def test_duplicate_replay_is_idempotent_and_bound_to_connection(self):
        bridge = self.bridge()
        calls = []
        bridge._post_enrollment_carrier = lambda route, payload: (
            calls.append((route, payload)) or (202, None))
        request_id, frame = self.carrier("challenge", challenge())
        first = bridge.submit_ble_write(frame, "connection-a")
        second = bridge.submit_ble_write(frame, "connection-a")
        self.assertEqual(second, first)
        self.assertEqual(len(calls), 1)

        with self.assertRaises(BleProtocolError):
            bridge.submit_ble_write(frame, "connection-b")
        changed_id, changed_frame = self.carrier(
            "reverse", {"schema": "openaps.ns-reverse-ready.v1", "nonce": "e" * 64},
            request_id=request_id)
        with self.assertRaises(BleProtocolError):
            bridge.submit_ble_write(changed_frame, "connection-a")
        self.assertEqual(len(calls), 1)

    def test_expiry_and_disconnect_prevent_endpoint_call_or_cross_generation_ack(self):
        now = [10.0]
        bridge = self.bridge(monotonic=lambda: now[0])
        calls = []
        bridge._post_enrollment_carrier = lambda route, payload: (
            calls.append((route, payload)) or (202, None))

        expired_id, expired_frame = self.carrier("challenge", challenge())
        prepared = bridge._prepare_ble_write(expired_frame, "connection-expired")
        generation = prepared[1]._ble_connection_generation
        now[0] += BLE_ENROLLMENT_CARRIER_LIFETIME_SECONDS + 0.001
        ack = bridge._execute_prepared_ble_write(prepared, "connection-expired", generation)
        self.assertEqual(ack["request_id"], expired_id)
        self.assertEqual(ack["status"], 503)
        self.assertEqual(calls, [])

        disconnected_id, disconnected_frame = self.carrier("reverse", {
            "schema": "openaps.ns-reverse-ready.v1",
            "nonce": "f" * 64,
        })
        prepared = bridge._prepare_ble_write(disconnected_frame, "connection-disconnected")
        generation = prepared[1]._ble_connection_generation
        bridge.clear_connection_state("connection-disconnected")
        ack = bridge._execute_prepared_ble_write(
            prepared, "connection-disconnected", generation)
        self.assertIsNone(ack)
        self.assertEqual(calls, [])
        self.assertNotEqual(
            bridge.ack_for_connection("connection-disconnected").get("request_id"),
            disconnected_id)
        with self.assertRaises(BleProtocolError):
            bridge.submit_ble_write(disconnected_frame, "connection-reused")

    def test_disconnect_during_endpoint_request_drops_private_result_body(self):
        bridge = self.bridge()
        request_id, frame = self.carrier("reverse", {
            "schema": "openaps.ns-reverse-ready.v1",
            "nonce": "f" * 64,
        })

        def disconnect_before_response(_route, _payload):
            bridge.clear_connection_state("connection-a")
            return 200, {"schema": "openaps.ns-reverse-challenge.v1", "challenge": challenge()}

        bridge._post_enrollment_carrier = disconnect_before_response
        ack = bridge.submit_ble_write(frame, "connection-a")
        self.assertIsNone(ack)
        self.assertIsNone(bridge._enrollment_carrier_requests[request_id]["ack"])
        self.assertNotEqual(
            bridge.ack_for_connection("connection-a").get("request_id"), request_id)

    def test_ordinary_ble_event_path_remains_clinical_and_separate(self):
        bridge = self.bridge()
        seen = []
        bridge.post_event = lambda event: (
            seen.append(event) or {"schema": "openaps.local.event_ack.v1", "event_id": "legacy"})
        event = {"schema": "openaps.local.event.v1", "event_id": "legacy"}
        ack = bridge.submit_ble_write(
            json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "connection-clinical")
        self.assertEqual(seen, [event])
        self.assertEqual(ack["schema"], "openaps.local.event_ack.v1")
        self.assertNotEqual(ack["schema"], ENROLLMENT_RESULT_SCHEMA)


if __name__ == "__main__":
    unittest.main()
