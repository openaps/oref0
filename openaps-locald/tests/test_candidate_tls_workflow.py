"""Synthetic policy fixture joins real proof owners, storage and loopback TLS.

This is deliberately NOT a production provenance provider. No live deployment
review, remote Nightscout, pump operation or clinical input is involved.
"""
import contextlib
import json
import os
import ssl
import struct
import unittest
import uuid

from openaps_locald.admission_record import Context
from openaps_locald.admission_candidate_archive import CandidateArchive
from openaps_locald.admission_candidate_commit import CandidateCommitCoordinator
from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.admission_owner import AdmissionOwner, LiveAdmissionContext
from openaps_locald.authorization_protocol import proof_authority_context_id
from openaps_locald.authorization_tls import TLSError
from openaps_locald.nightscout_write_proof import NightscoutWriteProofClient
from openaps_locald.write_challenge import ChallengeError
from tests import test_tls_http, test_admission_owner


class CandidateTLSWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_tls_http.TLSHTTPTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        test_tls_http.TLSHTTPTests.tearDownClass()

    def test_two_sided_proof_commit_health_then_retained_and_new_connection_denial(self):
        harness = test_tls_http.TLSHTTPTests()
        harness.setUp()
        self.addCleanup(harness.tearDown)
        f = harness.fixture
        authority = proof_authority_context_id("https://example.invalid/base")
        rows = {}
        class Anonymous:
            def request_bytes(self, *args, **kwargs):
                self_test.assertNotIn("api_secret", kwargs)
                return 401, b""
        self_test = self
        class SyntheticPublisherTransport:
            def __init__(self, identity):
                self.identity = identity
            def request_bytes(self, method, path, body=None, query=None, **kwargs):
                self_test.assertEqual(kwargs.get("api_secret"), "synthetic")
                if "/authorization/debug/" in path:
                    return 200, b'{"check":true}'
                if path == "/api/v1/status.json":
                    return 200, b'{"serverTimeEpoch":1000}'
                if method == "POST":
                    self_test.assertEqual(body["openaps_write_response"]["peer_credential_id"], self.identity.credential_id)
                    rows[body["identifier"]] = body
                    return 201, b"{}"
                row = rows.get(query["find[identifier]"])
                return 200, json.dumps([] if row is None else [row]).encode("utf-8")
        clients = {}
        for role, identity in (("phone", f.phone), ("rig", f.rig)):
            clients[role] = NightscoutWriteProofClient("https://example.invalid/base", identity, role,
                api_secret="synthetic", transport=SyntheticPublisherTransport(identity),
                anonymous_transport=Anonymous(), clock=lambda: f.now)
            self.addCleanup(clients[role].invalidate)
        policy, lease = test_admission_owner.synthetic_review_fixture(authority)
        generation = lease.generation
        current = [True]
        @contextlib.contextmanager
        def explicitly_synthetic_reviewed_policy_guard(context):
            if not current[0] or context.authority != authority or context.policy_generation != generation:
                raise TLSError("synthetic policy unavailable")
            yield
            if not current[0]:
                raise TLSError("synthetic policy changed")
        candidates = {}
        for role, peer_role, identity, peer in (("phone", "rig", f.phone, f.rig), ("rig", "phone", f.rig, f.phone)):
            client = clients[role]
            before = client.observe_enrollment_permissions()
            challenge = client.issue_challenge(peer.credential_id, peer_role)
            clients[peer_role].publish_own_response(challenge)
            receipt = client.read_fresh_peer_response(challenge["nonce"], peer.public_key_der)
            after = client.observe_enrollment_permissions()
            context = Context(authority, identity.credential_id, role, peer.credential_id,
                uuid.uuid4(), uuid.uuid4(), generation, "b" * 64)
            directory = os.path.join(harness.directory.name, role + "-candidate-store")
            os.mkdir(directory, 0o700)
            storage = AdmissionStorage(directory)
            if role == "rig":
                live_context = LiveAdmissionContext(context)
                def validate_persisted(expected):
                    self.assertEqual(expected, context)  # Explicit synthetic durable-context fixture.
                rig_owner = AdmissionOwner(client, storage, context, identity, live_context, lease,
                    validate_persisted, clock=lambda: f.now)
                self.addCleanup(rig_owner.invalidate)
                commit_id = rig_owner.admit_fresh(receipt, before, after)
            else:
                owner = CandidateCommitCoordinator(client, storage, context, identity, explicitly_synthetic_reviewed_policy_guard)
                commit_id = owner.commit_candidate(receipt, before, after).commit_id
            restored = CandidateArchive(storage.load()).candidate(context, identity)
            self.assertEqual(restored.commit_id, commit_id)
            candidates[role] = restored

        # Actual fresh-admission owner supplies TLS state, not a reconstructed
        # test snapshot or continuity initialized from persisted candidate bytes.
        self.assertEqual(candidates["phone"].proof.public_key_der, f.rig_hello.public_key_der)
        f.snapshot = rig_owner.snapshot(str(uuid.uuid4()))
        continuity = f.snapshot["continuity"]
        harness.start()
        peer = harness.peer(harness.request() + f.phone_hello.encode())
        self.assertIn(b" 101 ", harness.headers(peer))
        hello = b""
        while len(hello) < len(f.rig_hello.encode()):
            chunk = peer.recv(len(f.rig_hello.encode()) - len(hello))
            self.assertTrue(chunk)
            hello += chunk
        self.assertEqual(hello, f.rig_hello.encode())
        client, incoming, outgoing = f.client()
        for _ in range(64):
            ready = False
            try:
                client.do_handshake(); ready = True
            except ssl.SSLWantReadError:
                pass
            wire = outgoing.read()
            if wire:
                peer.sendall(wire)
            if ready:
                break
            incoming.write(peer.recv(65536))
        self.assertTrue(ready)
        def send_health(identifier):
            payload = json.dumps({"schema": "openaps.tls.request.v1", "request_id": identifier,
                "destination_credential_id": f.rig.credential_id, "method": "GET", "path": "/v1/health",
                "query": {}, "body": None}).encode("utf-8")
            client.write(struct.pack("!I", len(payload)) + payload)
            peer.sendall(outgoing.read())
        send_health("synthetic-before")
        result = bytearray()
        for _ in range(256):
            try:
                result.extend(client.read(65536))
            except ssl.SSLWantReadError:
                incoming.write(peer.recv(65536))
            if len(result) >= 4 and len(result) == struct.unpack("!I", result[:4])[0] + 4:
                break
        self.assertEqual(json.loads(result[4:].decode("utf-8"))["status"], 200)
        current[0] = False
        live_context.invalidate()  # Owner-scoped settings/key lifecycle, not manual token invalidation.
        with self.assertRaises(ChallengeError):
            rig_owner.snapshot(str(uuid.uuid4()))
        send_health("synthetic-after")
        try:
            rejected = peer.recv(65536)
        except ConnectionResetError:
            rejected = b""
        self.assertEqual(rejected, b"")
        retained = dict(f.snapshot)
        with self.assertRaises(TLSError):
            f.server()  # Same retained snapshot cannot create a new TLS owner.
        self.assertIs(retained["continuity"], continuity)
