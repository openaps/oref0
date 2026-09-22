import copy
import json
import struct
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from openaps_locald.http_api import make_handler
from openaps_locald.tls_clinical import TLSClinicalSession
from openaps_locald.authorization_tls import TLSError
from tests import test_authorization_tls as tls_fixture


class ClinicalDispatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="openaps-dispatch-test-")
        self.handler = make_handler({"db_path": os.path.join(self.directory.name, "events.sqlite3"),
                                     "rig_id": "rig-placeholder", "patient_id": "patient-placeholder"})
        self.dispatch = self.handler.clinical_dispatcher
        self.effects = []
        self.dispatch.materialize = self.materialize
        self.dispatch.collector_details = lambda event, config: {}
        self.dispatch.log = lambda message: None
        self.event = {"schema": "openaps.local.event.v1", "event_id": "synthetic-event",
                      "patient_id": "patient-placeholder", "event_type": "temp_target",
                      "created_at": "2026-01-01T00:00:00Z", "effective_at": "2026-01-01T00:00:00Z",
                      "payload": {"target_bottom_mgdl": 100, "target_top_mgdl": 100,
                                  "duration_minutes": 30}}

    def tearDown(self):
        self.handler.db.close()
        self.directory.cleanup()

    def materialize(self, event, config):
        self.effects.append(event["event_id"])
        return {"materialization": "synthetic-only"}

    def test_retry_across_legacy_and_authenticated_entry_is_once(self):
        first = self.dispatch.process_legacy([self.event])
        second = self.dispatch.process_authenticated([self.event], lambda: None)
        self.assertEqual(first[0]["ack_status"], "stored")
        self.assertEqual(second[0]["ack_status"], "duplicate")
        self.assertEqual(self.effects, ["synthetic-event"])

    def test_concurrent_authenticated_routes_share_serialization(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.dispatch.process_authenticated([self.event], lambda: None), range(2)))
        self.assertEqual(sorted(result[0]["ack_status"] for result in results), ["duplicate", "stored"])
        self.assertEqual(self.effects, ["synthetic-event"])

    def test_failed_live_authorization_has_no_storage_or_effect(self):
        def reject():
            raise PermissionError("synthetic trust removed")
        with self.assertRaises(PermissionError):
            self.dispatch.process_authenticated([self.event], reject)
        self.assertIsNone(self.handler.db.get_event(self.event["event_id"]))
        self.assertEqual(self.effects, [])

    def test_recheck_before_each_batch_event(self):
        second = copy.deepcopy(self.event)
        second["event_id"] = "synthetic-second"
        checks = []
        def authorize():
            checks.append(True)
            if len(checks) > 1:
                raise PermissionError("synthetic generation changed")
        with self.assertRaises(PermissionError):
            self.dispatch.process_authenticated([self.event, second], authorize)
        self.assertEqual(self.effects, ["synthetic-event"])
        self.assertIsNone(self.handler.db.get_event(second["event_id"]))

    def test_wrong_patient_remains_rejected(self):
        self.event["patient_id"] = "foreign-placeholder"
        result = self.dispatch.process_authenticated([self.event], lambda: None)
        self.assertEqual(result[0]["ack_status"], "rejected_wrong_patient")
        self.assertEqual(self.effects, [])

    def test_no_request_boolean_can_stand_for_authorization(self):
        with self.assertRaises(ValueError):
            self.dispatch.process_authenticated([self.event], True)
        self.assertEqual(self.effects, [])

    def test_read_routes_match_authenticated_results(self):
        reads = self.handler.clinical_reads
        for key in ("status", "device_status", "materialization", "pump_history"):
            reads.providers[key] = lambda *args, **kwargs: {"synthetic": True}
        self.dispatch.process_legacy([self.event])
        paths = ("/v1/health", "/v1/rig", "/v1/status", "/v1/device-status",
                 "/v1/devicestatus", "/v1/materialization", "/v1/events",
                 "/v1/bg-readings", "/v1/bg-readings/latest", "/v1/pumphistory",
                 "/v1/pump-history", "/v1/events/synthetic-event",
                 "/v1/events/synthetic-event/acks", "/v1/events/missing", "/missing")
        for path in paths:
            self.assertEqual(reads.read_authenticated(path, {}, lambda: None),
                             reads.read_legacy(path, {}), path)

    def test_failed_authorization_never_calls_reader(self):
        reads = self.handler.clinical_reads
        calls = []
        reads.providers["device_status"] = lambda config: calls.append(True)
        def reject():
            raise PermissionError("synthetic trust unavailable")
        with self.assertRaises(PermissionError):
            reads.read_authenticated("/v1/device-status", {}, reject)
        self.assertEqual(calls, [])

    def test_trust_change_during_read_prevents_response_release(self):
        reads = self.handler.clinical_reads
        current = [True]
        def read(config):
            current[0] = False
            return {"synthetic": "must not be released"}
        def authorize():
            if not current[0]:
                raise PermissionError("synthetic generation changed")
        reads.providers["device_status"] = read
        with self.assertRaises(PermissionError):
            reads.read_authenticated("/v1/device-status", {}, authorize)

    def test_read_authorization_is_rechecked(self):
        calls = []
        result = self.handler.clinical_reads.read_authenticated("/v1/health", {}, lambda: calls.append(True))
        self.assertEqual(result[0], 200)
        self.assertEqual(calls, [True, True])

    def test_reads_share_event_serialization_lock(self):
        self.assertIs(self.handler.clinical_reads.lock, self.dispatch.lock)

    def test_read_requires_live_callback(self):
        with self.assertRaises(ValueError):
            self.handler.clinical_reads.read_authenticated("/v1/health", {}, True)

    @contextmanager
    def tls_pair(self, authenticated_contact=None):
        # An isolated subclass reuses the synthetic TLS fixture without sharing
        # the test class's identity directory with other test cases.
        fixture_type = type("ClinicalTLSFixture", (tls_fixture.TLSReceiverTests,), {})
        fixture_type.setUpClass()
        fixture = fixture_type()
        fixture.setUp()
        try:
            server = fixture.server()
            client, incoming, outgoing = fixture.connect(server)
            session = TLSClinicalSession(
                server,
                self.dispatch,
                self.handler.clinical_reads,
                authenticated_contact=authenticated_contact,
            )
            yield fixture, session, client, incoming, outgoing
        finally:
            fixture.tearDown()
            fixture_type.tearDownClass()

    def tls_request(self, fixture, method="GET", path="/v1/health", body=None):
        return {"schema": "openaps.tls.request.v1", "request_id": "synthetic-request",
                "destination_credential_id": fixture.rig.credential_id,
                "method": method, "path": path, "query": {}, "body": body}

    def exchange(self, session, client, incoming, outgoing, request):
        encoded = json.dumps(request).encode("utf-8")
        client.write(struct.pack("!I", len(encoded)) + encoded)
        wire = outgoing.read()
        for offset in range(0, len(wire), 13):
            incoming.write(session.receive(wire[offset:offset + 13]))
        response = client.read(65536)
        self.assertEqual(struct.unpack("!I", response[:4])[0], len(response) - 4)
        return json.loads(response[4:].decode("utf-8"))

    def test_real_tls_dispatch_read_write_and_retry(self):
        with self.tls_pair() as (fixture, session, client, incoming, outgoing):
            response = self.exchange(session, client, incoming, outgoing, self.tls_request(fixture))
            self.assertEqual(response["status"], 200)
            request = self.tls_request(fixture, "POST", "/v1/events", {"events": [self.event]})
            first = self.exchange(session, client, incoming, outgoing, request)
            second = self.dispatch.process_legacy([self.event])
            self.assertEqual(first["body"]["acks"][0]["ack_status"], "stored")
            self.assertEqual(second[0]["ack_status"], "duplicate")
            self.assertEqual(self.effects, ["synthetic-event"])

    def test_authenticated_contact_runs_only_after_valid_request(self):
        contacts = []
        with self.tls_pair(authenticated_contact=lambda: contacts.append("authenticated")) as (
                fixture, session, client, incoming, outgoing):
            response = self.exchange(session, client, incoming, outgoing,
                                     self.tls_request(fixture))
            self.assertEqual(response["status"], 200)
            self.assertEqual(contacts, ["authenticated"])

        contacts = []
        with self.tls_pair(authenticated_contact=lambda: contacts.append("authenticated")) as (
                fixture, session, client, incoming, outgoing):
            request = self.tls_request(fixture)
            request["destination_credential_id"] = fixture.phone.credential_id
            with self.assertRaises(TLSError):
                self.exchange(session, client, incoming, outgoing, request)
            self.assertEqual(contacts, [])

    def test_joined_legacy_and_tls_idempotence_correlation_and_no_downgrade(self):
        # A temp target exercises only this harness's synthetic materializer;
        # no CGM/collector process-control command is installed or invoked.
        self.assertEqual(self.event["event_type"], "temp_target")
        legacy = self.dispatch.process_legacy([self.event])[0]
        self.assertEqual(legacy["ack_status"], "stored")
        with self.tls_pair() as (fixture, session, client, incoming, outgoing):
            request = self.tls_request(fixture, "POST", "/v1/events", {"events": [self.event]})
            request["request_id"] = self.event["event_id"]
            response = self.exchange(session, client, incoming, outgoing, request)
            ack = response["body"]["acks"][0]
            self.assertEqual(response["request_id"], self.event["event_id"])
            self.assertEqual(ack["event_id"], legacy["event_id"])
            self.assertEqual(ack["ack_status"], "duplicate")
            self.assertTrue(ack["details"]["duplicate"])
            self.assertEqual(self.effects, [self.event["event_id"]])

        rejected = copy.deepcopy(self.event)
        rejected["event_id"] = "synthetic-wrong-destination"
        legacy_calls = []
        original_legacy = self.dispatch.process_legacy
        self.dispatch.process_legacy = lambda events, log_prefix="POST /v1/events": legacy_calls.append(events)
        try:
            with self.tls_pair() as (fixture, session, client, incoming, outgoing):
                request = self.tls_request(fixture, "POST", "/v1/events", {"events": [rejected]})
                request["destination_credential_id"] = fixture.phone.credential_id
                with self.assertRaises(TLSError):
                    self.exchange(session, client, incoming, outgoing, request)
        finally:
            self.dispatch.process_legacy = original_legacy
        self.assertEqual(legacy_calls, [])
        self.assertIsNone(self.handler.db.get_event(rejected["event_id"]))
        self.assertEqual(self.effects, [self.event["event_id"]])

    def test_real_tls_wrong_destination_never_dispatches(self):
        with self.tls_pair() as (fixture, session, client, incoming, outgoing):
            request = self.tls_request(fixture, "POST", "/v1/events", {"events": [self.event]})
            request["destination_credential_id"] = fixture.phone.credential_id
            with self.assertRaises(TLSError):
                self.exchange(session, client, incoming, outgoing, request)
            self.assertEqual(self.effects, [])
            self.assertTrue(session.tls.closed)

    def test_real_tls_trust_removed_before_dispatch(self):
        with self.tls_pair() as (fixture, session, client, incoming, outgoing):
            request = self.tls_request(fixture, "POST", "/v1/events", {"events": [self.event]})
            fixture.snapshot = None
            with self.assertRaises(TLSError):
                self.exchange(session, client, incoming, outgoing, request)
            self.assertEqual(self.effects, [])

    def test_real_tls_malformed_application_frames_close(self):
        for data in (struct.pack("!I", 65533), struct.pack("!I", 0),
                     struct.pack("!I", 2) + b"[]",
                     struct.pack("!I", 13) + b'{"x":1,"x":2}'):
            with self.tls_pair() as (fixture, session, client, incoming, outgoing):
                client.write(data)
                with self.assertRaises((ValueError, TLSError)):
                    session.receive(outgoing.read())
                self.assertTrue(session.tls.closed)
                self.assertEqual(self.effects, [])

    def test_partial_request_is_cleared_on_session_expiry(self):
        with self.tls_pair() as (fixture, session, client, incoming, outgoing):
            client.write(struct.pack("!I", 100) + b"{")
            session.receive(outgoing.read())
            self.assertTrue(session.pending)
            fixture.now = 300
            with self.assertRaises(TLSError):
                session.tick()
            self.assertEqual(session.pending, bytearray())


if __name__ == "__main__":
    unittest.main()
