"""Actual proof/admission owners with synthetic NS replies and loopback HTTP."""
import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
import uuid

from openaps_locald.admission_owner import AdmissionOwner, LiveAdmissionContext
from openaps_locald.admission_record import Context
from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.http_api import ThreadedHTTPServer, make_handler
from openaps_locald.reverse_enrollment import ReverseEnrollmentWorkflow, BEGIN, READY, CHALLENGE
from openaps_locald.write_challenge import signed_response, response_envelope, ChallengeError
from tests.test_admission_owner import synthetic_review_fixture
from tests import test_nightscout_write_proof


class ReverseEnrollmentTests(unittest.TestCase):
    def fixture(self):
        f = test_nightscout_write_proof.ProofIOTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        class Anonymous:
            def request_bytes(self, *args, **kwargs):
                return 401, b""
        client = f.client(f.rig, "rig", anonymous_transport=Anonymous())
        policy, lease = synthetic_review_fixture(f.authority)
        context = Context(f.authority, f.rig.credential_id, "rig", f.phone.credential_id,
            uuid.uuid4(), uuid.uuid4(), lease.generation, lease.review_sha256)
        directory = tempfile.TemporaryDirectory(prefix="openaps-reverse-candidates-")
        self.addCleanup(directory.cleanup)
        storage = AdmissionStorage(directory.name)
        live = LiveAdmissionContext(context)
        owner = AdmissionOwner(client, storage, context, f.rig, live, lease, lambda expected: None,
                               clock=lambda: f.time)
        workflow = ReverseEnrollmentWorkflow(client, f.rig, f.authority, lambda key: owner, clock=lambda: f.time)
        body = {"schema": BEGIN, "challenge": f.challenge,
                "phone_public_key_der": base64.b64encode(f.phone.public_key_der).decode("ascii")}
        self.addCleanup(workflow.invalidate)
        return f, client, owner, live, policy, storage, workflow, body

    def begin(self, f, workflow, body):
        f.replies = [(200, b'{"check":true}')]
        code, result = workflow.handle(body)
        self.assertEqual(code, 200)
        self.assertEqual(result["schema"], CHALLENGE)
        return result["challenge"]

    def ready_replies(self, f, challenge):
        response = signed_response(challenge, f.phone, f.authority, "phone")
        f.replies = [(200, b"[" + response_envelope(challenge, response, 1000) + b"]"),
                     (200, b'{"check":true}')]

    def test_fresh_nonce_missing_row_retry_and_real_owner_commit(self):
        f, client, owner, live, policy, storage, workflow, body = self.fixture()
        b = self.begin(f, workflow, body)
        self.assertNotEqual(b["nonce"], f.challenge["nonce"])
        self.assertEqual(b["verifier_credential_id"], f.rig.credential_id)
        self.assertEqual(b["peer_credential_id"], f.phone.credential_id)
        count = len(f.calls)
        self.assertEqual(workflow.handle(body), (200, {"schema": CHALLENGE, "challenge": b}))
        self.assertEqual(len(f.calls), count)
        f.replies = [(200, b"[]")]
        ready = {"schema": READY, "nonce": b["nonce"]}
        self.assertEqual(workflow.handle(ready), (425, None))
        self.assertEqual(workflow.handle({"schema": READY, "nonce": "0" * 64}), (400, None))
        self.ready_replies(f, b)
        self.assertEqual(workflow.handle(ready), (202, None))
        self.assertIsNotNone(storage.load())
        self.assertEqual(owner.snapshot(str(uuid.uuid4()))["peer_credential_id"], f.phone.credential_id)
        count = len(f.calls)
        self.assertEqual(workflow.handle(ready), (202, None))
        self.assertEqual(len(f.calls), count)
        f.time = 120
        self.assertEqual(workflow.handle(ready), (400, None))
        owner.snapshot(str(uuid.uuid4())) # Expiring a completed tombstone is not revocation.

    def test_wrong_key_authority_and_busy_original_never_get_provenance(self):
        f, client, owner, live, policy, storage, workflow, body = self.fixture()
        wrong = dict(body, phone_public_key_der=base64.b64encode(f.rig.public_key_der).decode("ascii"))
        self.assertEqual(workflow.handle(wrong), (400, None))
        wrong = dict(body, challenge=dict(body["challenge"], authority_context_id="ns_" + "a" * 64))
        self.assertEqual(workflow.handle(wrong), (400, None))
        self.assertEqual(f.calls, [])
        self.begin(f, workflow, body)
        other = dict(body, challenge=dict(body["challenge"], nonce="1" * 64))
        self.assertEqual(workflow.handle(other), (429, None))
        with self.assertRaises(ChallengeError):
            owner.snapshot(str(uuid.uuid4()))

    def test_expiry_cancellation_policy_and_settings_discard_pending_without_commit(self):
        for mode in ("expiry", "cancel", "policy", "settings"):
            f, client, owner, live, policy, storage, workflow, body = self.fixture()
            b = self.begin(f, workflow, body)
            if mode == "expiry":
                f.time = 120
            elif mode == "cancel":
                workflow.invalidate()
            elif mode == "policy":
                policy.invalidate()
            else:
                live.invalidate()
            code, _ = workflow.handle({"schema": READY, "nonce": b["nonce"]})
            self.assertIn(code, (400, 503))
            self.assertIsNone(storage.load())
            with self.assertRaises(ChallengeError):
                owner.snapshot(str(uuid.uuid4()))

    def test_factory_cannot_hand_public_attempt_an_active_owner(self):
        f, client, owner, live, policy, storage, workflow, body = self.fixture()
        b = self.begin(f, workflow, body)
        self.ready_replies(f, b)
        self.assertEqual(workflow.handle({"schema": READY, "nonce": b["nonce"]}), (202, None))
        active = owner.snapshot(str(uuid.uuid4()))
        different_attempt = ReverseEnrollmentWorkflow(client, f.rig, f.authority,
            lambda key: owner, clock=lambda: f.time)
        count = len(f.calls)
        self.assertEqual(different_attempt.handle(body), (503, None))
        self.assertEqual(len(f.calls), count)
        active["continuity"].require_current(tuple(active[key] for key in
            ("authority_context_id", "local_credential_id", "peer_credential_id", "connection_generation", "trust_generation")))
        owner.snapshot(str(uuid.uuid4()))

    def test_loopback_route_uses_real_workflow_and_returns_only_challenge_or_empty_status(self):
        f, client, owner, live, policy, storage, workflow, body = self.fixture()
        directory = tempfile.TemporaryDirectory(prefix="openaps-reverse-http-")
        self.addCleanup(directory.cleanup)
        handler = make_handler({"db_path": os.path.join(directory.name, "events.sqlite3"),
            "rig_id": "rig-placeholder", "patient_id": "patient-placeholder", "auth_token": "synthetic"},
            enrollment_reverse_workflow=workflow, enrollment_clock=lambda: f.time)
        server = ThreadedHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02))
        thread.daemon = True
        thread.start()
        def post(value, path="/v3/enrollment/reverse"):
            connection = http.client.HTTPConnection(*server.server_address, timeout=3)
            try:
                connection.request("POST", path, json.dumps(value).encode("ascii"), {"Content-Type": "application/json"})
                response = connection.getresponse()
                data = response.read(1025)
                self.assertLessEqual(len(data), 1024)
                return response.status, json.loads(data.decode("ascii")) if data else None
            finally:
                connection.close()
        try:
            f.replies = [(200, b'{"check":true}')]
            code, result = post(body)
            self.assertEqual(code, 200)
            self.assertEqual(set(result), {"schema", "challenge"})
            b = result["challenge"]
            self.ready_replies(f, b)
            self.assertEqual(post({"schema": READY, "nonce": b["nonce"]}), (202, None))
            owner.snapshot(str(uuid.uuid4()))
            self.assertEqual(post(f.challenge, path="/v3/enrollment/challenge"), (503, None))
        finally:
            server.shutdown(); server.server_close(); thread.join(2); handler.db.close()

    def test_dynamic_complete_pair_activates_reverse_route(self):
        f, client, owner, live, policy, storage, workflow, body = self.fixture()
        directory = tempfile.TemporaryDirectory(prefix="openaps-reverse-dynamic-http-")
        self.addCleanup(directory.cleanup)
        calls = []
        pair = [(None, None)]
        handler = make_handler({"db_path": os.path.join(directory.name, "events.sqlite3"),
            "rig_id": "rig-placeholder", "patient_id": "patient-placeholder", "auth_token": "synthetic"},
            enrollment_components_provider=lambda: pair[0], enrollment_clock=lambda: f.time)
        server = ThreadedHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02))
        thread.daemon = True
        thread.start()
        def post(value):
            connection = http.client.HTTPConnection(*server.server_address, timeout=3)
            try:
                connection.request("POST", "/v3/enrollment/reverse", json.dumps(value).encode("ascii"),
                    {"Content-Type": "application/json"})
                response = connection.getresponse()
                data = response.read()
                return response.status, json.loads(data.decode("ascii")) if data else None
            finally:
                connection.close()
        try:
            self.assertEqual(post(body), (503, None))
            pair[0] = (lambda challenge: calls.append(challenge), None)
            self.assertEqual(post(body), (503, None))
            pair[0] = (lambda challenge: calls.append(challenge), workflow)
            f.replies = [(200, b'{"check":true}')]
            code, result = post(body)
            self.assertEqual(code, 200)
            self.assertEqual(result["schema"], CHALLENGE)
            self.assertEqual(calls, [])
        finally:
            server.shutdown(); server.server_close(); thread.join(2); handler.db.close()
