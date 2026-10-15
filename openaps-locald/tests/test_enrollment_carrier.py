"""Real loopback HTTP fixture; synthetic public challenge only, no NS access."""
import http.client
import json
import os
import socket
import tempfile
import threading
import time
import unittest

from openaps_locald.enrollment_carrier import EnrollmentPublicationWorker, _publication_failure_code
from openaps_locald.http_api import ThreadedHTTPServer, make_handler
from openaps_locald.nightscout_authorization import NightscoutAuthorizationError
from openaps_locald.reverse_enrollment import ReverseEnrollmentWorkflow
from openaps_locald.write_challenge import ChallengeError, fresh_challenge


class EnrollmentCarrierTests(unittest.TestCase):
    def test_publication_failure_codes_never_include_untrusted_exception_text(self):
        self.assertEqual(_publication_failure_code(
            NightscoutAuthorizationError("proof_publication", status=503)),
            "proof_publication_http_503")
        self.assertEqual(_publication_failure_code(
            ChallengeError("proof participant context mismatch")),
            "proof_context_mismatch")
        self.assertEqual(_publication_failure_code(
            Exception("token=private-example")), "publication_unexpected")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="openaps-enrollment-http-test-")
        self.server = None
        self.unblock = threading.Event()
        self.calls = []
        self.challenge = fresh_challenge("ns_" + "a" * 64, "b" * 64, "phone", "c" * 64, "rig")

    def tearDown(self):
        self.unblock.set()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)
            self.handler.db.close()
        self.directory.cleanup()

    def start(self, publisher=None, shortened_deadline=False, provider=None):
        handler = make_handler({"db_path": os.path.join(self.directory.name, "events.sqlite3"),
            "rig_id": "rig-placeholder", "patient_id": "patient-placeholder",
            "auth_token": "synthetic-legacy-token"}, enrollment_challenge_publisher=publisher,
            enrollment_clock=time.monotonic,
            enrollment_components_provider=provider) # Explicit host fixture, not production fallback.
        if shortened_deadline:
            class DeadlineFixture(handler):
                def _http_enrollment_challenge(self):
                    self._carrier_started -= 19.9
                    return super(DeadlineFixture, self)._http_enrollment_challenge()
            handler = DeadlineFixture
        self.handler = handler
        def no_clinical(*args, **kwargs):
            raise AssertionError("enrollment invoked clinical dispatcher")
        handler.clinical_dispatcher.process_legacy = no_clinical
        self.server = ThreadedHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02))
        self.thread.daemon = True
        self.thread.start()

    def request(self, body=None, headers=None, path="/v3/enrollment/challenge"):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            payload = json.dumps(self.challenge).encode("ascii") if body is None else body
            fields = {"Content-Type": "application/json"}
            fields.update(headers or {})
            connection.request("POST", path, body=payload, headers=fields)
            response = connection.getresponse()
            data = response.read(1025)
            self.assertEqual(data, b"")
            self.assertEqual(response.getheader("Content-Length"), "0")
            return response.status
        finally:
            connection.close()

    def test_publication_success_no_bearer_no_result_or_clinical_payload(self):
        def publisher(challenge):
            self.calls.append(challenge)
            return {"must_not_escape": "synthetic-response"}
        self.start(publisher)
        self.assertEqual(self.request(), 202)
        self.assertEqual(self.calls, [self.challenge])

    def test_disabled_without_authentication_is_nonclinical_unavailable(self):
        self.start()
        self.assertEqual(self.request(), 503)

    def test_dynamic_components_are_all_or_nothing_per_request(self):
        workflow = ReverseEnrollmentWorkflow(None, None, "ns_" + "a" * 64, lambda key: None)
        state = [(None, None)]
        snapshots = []
        def provider():
            snapshots.append(state[0])
            return state[0]
        self.start(provider=provider)
        self.assertEqual(self.request(), 503)
        state[0] = (lambda challenge: self.calls.append(challenge), None)
        self.assertEqual(self.request(), 503)
        self.assertEqual(self.calls, [])
        state[0] = (lambda challenge: self.calls.append(challenge), workflow)
        self.assertEqual(self.request(), 202)
        self.assertEqual(self.calls, [self.challenge])
        self.assertEqual(len(snapshots), 3) # Exactly one component snapshot per request.

    def test_duplicate_framing_header_and_nonexact_path_never_publish(self):
        self.start(lambda challenge: self.calls.append(challenge))
        peer = socket.create_connection(self.server.server_address, timeout=3)
        try:
            peer.sendall(b"POST /v3/enrollment/challenge HTTP/1.1\r\nHost: example.invalid\r\n"
                b"Content-Type: application/json\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\nx")
            response = http.client.HTTPResponse(peer)
            response.begin()
            self.assertEqual(response.status, 400)
            self.assertEqual(response.read(), b"")
        finally:
            peer.close()
        self.assertEqual(self.request(path="/v3/enrollment/challenge?unexpected=1"), 400)
        self.assertEqual(self.calls, [])

    def test_duplicate_unknown_role_oversized_and_credentials_fail_closed(self):
        self.start(lambda challenge: self.calls.append(challenge))
        original = json.dumps(self.challenge).encode("ascii")
        duplicate = b'{"schema":"openaps.ns-write-challenge.v1",' + original[1:]
        unknown = dict(self.challenge, unexpected="value")
        wrong_role = dict(self.challenge, verifier_device_kind="rig", peer_device_kind="phone")
        for data in (duplicate, json.dumps(unknown).encode("ascii"), json.dumps(wrong_role).encode("ascii"), b" " * 4097):
            self.assertEqual(self.request(body=data), 400)
        self.assertEqual(self.request(headers={"Authorization": "Bearer synthetic"}), 400)
        self.assertEqual(self.request(headers={"Transfer-Encoding": "chunked"}), 400)
        self.assertEqual(self.calls, [])

    def test_busy_worker_and_callback_failure_have_fixed_status(self):
        entered = threading.Event()
        def publisher(challenge):
            self.calls.append(challenge)
            entered.set()
            self.unblock.wait(2)
            raise ValueError("sensitive callback error must not escape")
        self.start(publisher)
        first = []
        thread = threading.Thread(target=lambda: first.append(self.request()))
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(self.request(), 429)
        self.unblock.set()
        thread.join(3)
        self.assertEqual(first, [503])
        self.assertEqual(len(self.calls), 1)

    def test_timeout_retains_worker_until_actual_exit(self):
        entered = threading.Event()
        def publisher(challenge):
            self.calls.append(challenge)
            entered.set()
            self.unblock.wait(2)
        self.start(publisher, shortened_deadline=True)
        self.assertEqual(self.request(), 503)
        self.assertTrue(entered.is_set())
        self.assertEqual(self.request(), 429)
        self.assertEqual(len(self.calls), 1)
        self.unblock.set()

    def test_shared_attempt_bucket_bounds_repeated_publications(self):
        self.start(lambda challenge: self.calls.append(challenge))
        statuses = [self.request() for _ in range(7)]
        self.assertEqual(statuses, [202] * 6 + [429])
        self.assertEqual(len(self.calls), 6)

    def test_worker_reaps_only_terminal_callback_before_new_work(self):
        entered = threading.Event()
        def publisher(challenge):
            entered.set()
            self.unblock.wait(1)
        owner = EnrollmentPublicationWorker(publisher, clock=time.monotonic)
        self.assertEqual(owner.publish(self.challenge, time.monotonic() + 0.03), 503)
        self.assertTrue(entered.is_set())
        self.assertEqual(owner.publish(self.challenge, time.monotonic() + 0.1), 429)
        self.unblock.set()
        owner.worker.join(1)
        self.assertEqual(owner.publish(self.challenge, time.monotonic() + 1), 202)

    def test_worker_clock_regression_stays_failed_without_callback(self):
        now = [10.0]
        calls = []
        owner = EnrollmentPublicationWorker(lambda challenge: calls.append(challenge), clock=lambda: now[0])
        self.assertEqual(owner.publish(self.challenge, 20), 202)
        owner.worker.join(1)
        now[0] = 9
        self.assertEqual(owner.publish(self.challenge, 20), 503)
        now[0] = 11
        self.assertEqual(owner.publish(self.challenge, 20), 503)
        self.assertEqual(len(calls), 1)
