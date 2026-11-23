import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.authorization_protocol import proof_authority_context_id, realm_id_for_nightscout
from openaps_locald.nightscout_authorization import NightscoutAuthorizationError
from openaps_locald.nightscout_write_proof import NightscoutWriteProofClient
from openaps_locald.proof_commit import ProofCommitCoordinator
from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.proof_archive import ProofArchive
from openaps_locald.write_challenge import ChallengeError, fresh_challenge, signed_response, response_envelope


class ProofIOTests(unittest.TestCase):
    def test_path_aware_authority_vectors_and_legacy_separation(self):
        base = proof_authority_context_id("https://example.invalid/base")
        self.assertEqual(base, "ns_3f7593445b1c1525b167e03161ff7ea9407bb133ab924f24c99c199822091b70")
        self.assertEqual(base, proof_authority_context_id("https://EXAMPLE.invalid:443/base/"))
        self.assertNotEqual(base, proof_authority_context_id("https://example.invalid/other"))
        self.assertNotEqual(base, realm_id_for_nightscout("https://example.invalid/base"))
        self.assertEqual(proof_authority_context_id("https://[::1]:443/base/"), "ns_9698be89db037c52c4c8fc6979a99135c2bd85599dbcce53d8864e599d8d7744")
        self.assertEqual(proof_authority_context_id("https://example.invalid/a%20b"), "ns_9fa5c1f7ac7c4a983f316d3dd38d8e0b2f5b0d5b2d41c528112b74f29f1f084d")
        with self.assertRaises(Exception):
            proof_authority_context_id("http://example.invalid:57257/base")
        legacy = proof_authority_context_id(
            "http://example.invalid:57257/base", allow_insecure_http=True)
        self.assertNotEqual(base, legacy)
        self.assertNotEqual(legacy, proof_authority_context_id(
            "http://example.invalid/base", allow_insecure_http=True))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="openaps-proof-io-")
        self.addCleanup(self.directory.cleanup)
        self.phone = DeviceIdentity(os.path.join(self.directory.name, "phone"))
        self.rig = DeviceIdentity(os.path.join(self.directory.name, "rig"))
        self.url = "https://example.invalid/base"
        self.authority = proof_authority_context_id(self.url)
        self.challenge = fresh_challenge(self.authority, self.phone.credential_id, "phone", self.rig.credential_id, "rig")
        self.time = 0.0
        self.calls, self.replies = [], []
        test = self
        class Transport:
            def request_bytes(self, method, path, **kwargs):
                test.calls.append((method, path, kwargs))
                reply = test.replies.pop(0)
                return reply() if callable(reply) else reply
        self.transport = Transport()

    def client(self, identity, kind, token=False, anonymous_transport=None):
        client = NightscoutWriteProofClient(self.url, identity, kind,
            access_token="synthetic" if token else None, api_secret=None if token else "synthetic",
            clock=lambda: self.time, transport=self.transport, anonymous_transport=anonymous_transport)
        if token:
            client._jwt = SimpleNamespace(get_lease=lambda: SimpleNamespace(token="synthetic-jwt"), invalidate=lambda: None)
        return client

    def test_key_change_before_challenge_permanently_invalidates_owner(self):
        client = self.client(self.phone, "phone")
        client._identity = self.rig
        with self.assertRaises(ChallengeError):
            client.issue_challenge(self.rig.credential_id, "rig")
        client._identity = self.phone
        with self.assertRaises(ChallengeError):
            client.issue_challenge(self.rig.credential_id, "rig")
        self.assertEqual(self.calls, [])

    def test_challenge_issuance_respects_operation_ownership(self):
        client = self.client(self.phone, "phone")
        client._operation.acquire()
        try:
            with self.assertRaises(ChallengeError):
                client.issue_challenge(self.rig.credential_id, "rig")
        finally:
            client._operation.release()
        self.assertIsNotNone(client.issue_challenge(self.rig.credential_id, "rig"))

    def test_permission_observations_keep_anonymous_transport_credential_free(self):
        for token in (False, True):
            for status, expected in ((401, "denied_known_writes"), (200, "public_write"), (403, "inconclusive")):
                calls = []
                class Anonymous:
                    def request_bytes(self, method, path, **kwargs):
                        calls.append((method, path, kwargs))
                        return status, b'{"check":true}'
                client = self.client(self.phone, "phone", token, Anonymous())
                self.replies = [(200, b'{"check":true}')]
                result = client.observe_enrollment_permissions()
                self.assertEqual(result.outcome, expected)
                self.assertEqual(result.authority_context_id, self.authority)
                self.assertEqual(result.owner_generation, client._owner_generation)
                self.assertEqual(len(calls), 1 if status == 200 else 2)
                self.assertTrue(all(method == "GET" and not kwargs for method, path, kwargs in calls))
                self.assertIn("bearer" if token else "api_secret", self.calls[-1][2])
                client.invalidate()
                with self.assertRaises(ChallengeError):
                    client.observe_enrollment_permissions()

    def test_permission_control_malformed_or_denied_never_probes_anonymously(self):
        for body in (b'{"check":false}', b'{"check":true,"check":true}', b'{"check":1}', b'[]'):
            test = self
            class Anonymous:
                def request_bytes(self, *args, **kwargs):
                    test.fail("anonymous request after invalid control")
            client = self.client(self.phone, "phone", anonymous_transport=Anonymous())
            self.replies = [(200, body)]
            self.assertEqual(client.observe_enrollment_permissions().outcome, "inconclusive")

    def test_permission_observation_discards_late_or_invalidated_anonymous_results(self):
        for invalidated in (False, True):
            self.time = 0
            calls = []
            test = self
            class Anonymous:
                def request_bytes(self, method, path):
                    calls.append(path)
                    if invalidated:
                        client.invalidate()
                    else:
                        test.time = 60
                    return 401, b""
            client = self.client(self.phone, "phone", anonymous_transport=Anonymous())
            self.replies = [(200, b'{"check":true}')]
            with self.assertRaises(ChallengeError):
                client.observe_enrollment_permissions()
            self.assertEqual(len(calls), 1)

    def test_observation_proof_binding_requires_order_owner_and_workflow_deadline(self):
        status = [401]
        class Anonymous:
            def request_bytes(self, method, path):
                return status[0], b'{"check":true}'
        client = self.client(self.phone, "phone", anonymous_transport=Anonymous())
        self.replies = [(200, b'{"check":true}')]
        before = client.observe_enrollment_permissions()
        self.time = 5
        challenge = client.issue_challenge(self.rig.credential_id, "rig")
        response = signed_response(challenge, self.rig, self.authority, "rig")
        self.replies = [(200, b"[" + response_envelope(challenge, response, 1000) + b"]")]
        self.time = 10
        receipt = client.read_fresh_peer_response(challenge["nonce"], self.rig.public_key_der)
        self.time = 15
        self.replies = [(200, b'{"check":true}')]
        after = client.observe_enrollment_permissions()
        client.validate_observed_readback(receipt, before, after)
        # Join the real synthetic owner values to private file persistence.
        directory = tempfile.TemporaryDirectory(prefix="openaps-audit-commit-")
        self.addCleanup(directory.cleanup)
        storage = AdmissionStorage(directory.name)
        coordinator = ProofCommitCoordinator(client, storage, "b" * 64, self.phone)
        coordinator.commit_audit(receipt, before, after)
        saved = storage.load()
        coordinator.commit_audit(receipt, before, after)
        self.assertEqual(storage.load(), saved)
        restored = ProofArchive(saved).proof(self.authority, self.phone.credential_id,
            "phone", self.rig.credential_id, "b" * 64, self.phone)
        self.assertEqual(restored.response, receipt.response)
        test = self
        for mode in ("corrupt", "write-failed"):
            writes = []
            class FaultStorage:
                def load(self):
                    return b"malformed" if mode == "corrupt" else saved
                def replace(self, data, expecting):
                    writes.append(data)
                    raise OSError("synthetic storage failure")
            failed = ProofCommitCoordinator(client, FaultStorage(), "b" * 64, self.phone)
            with self.assertRaises((ChallengeError, OSError)):
                failed.commit_audit(receipt, before, after)
            self.assertEqual(len(writes), 1 if mode == "write-failed" else 0)
            self.time = 15
        for first, last in ((after, before), (before, before), (after, after)):
            with self.assertRaises(ChallengeError):
                client.validate_observed_readback(receipt, first, last)
        status[0] = 200
        self.replies = [(200, b'{"check":true}')]
        granted = client.observe_enrollment_permissions()
        with self.assertRaises(ChallengeError):
            client.validate_observed_readback(receipt, before, granted)
        status[0] = 401
        other = self.client(self.phone, "phone", anonymous_transport=Anonymous())
        self.replies = [(200, b'{"check":true}')]
        foreign = other.observe_enrollment_permissions()
        with self.assertRaises(ChallengeError):
            client.validate_observed_readback(receipt, before, foreign)
        self.time = 120
        with self.assertRaises(ChallengeError):
            client.validate_observed_readback(receipt, before, after)
        with self.assertRaises(ChallengeError):
            coordinator.commit_audit(receipt, before, after)
        self.assertEqual(storage.load(), saved)

    def test_publish_only_own_response_for_both_credential_modes(self):
        for token in (False, True):
            self.calls.clear()
            self.replies = [(200, json.dumps({"srvDate": 1000} if token else {"serverTimeEpoch": 1000}).encode()), (201, b"{}")]
            client = self.client(self.rig, "rig", token)
            identifier = client.publish_own_response(self.challenge)
            method, path, kwargs = self.calls[-1]
            self.assertEqual(method, "PUT" if token else "POST")
            self.assertEqual(kwargs["body"]["identifier"], identifier)
            self.assertEqual(kwargs["body"]["openaps_write_response"]["peer_credential_id"], self.rig.credential_id)
            self.assertIn("bearer" if token else "api_secret", kwargs)
            self.assertNotIn("subject", kwargs["body"])
        with self.assertRaises(ChallengeError):
            self.client(self.phone, "phone").publish_own_response(self.challenge)

    def test_independent_readback_verifies_signature_without_cache_mutation(self):
        response = signed_response(self.challenge, self.rig, self.authority, "rig")
        self.replies = [(200, b"[" + response_envelope(self.challenge, response, 1000) + b"]")]
        client = self.client(self.phone, "phone")
        self.assertEqual(client.read_peer_response(self.challenge, self.rig.public_key_der), response)
        self.assertEqual(self.calls[0][0], "GET")
        self.assertFalse(os.path.exists(self.phone.peer_directory))

    def test_legacy_lookup_rejects_duplicates_and_accepts_empty_only_as_absent(self):
        client = self.client(self.phone, "phone")
        self.replies = [(200, b"[]")]
        self.assertIsNone(client.read_peer_response(self.challenge, self.rig.public_key_der))
        self.assertEqual(self.calls[-1][2]["query"]["count"], "2")
        response = signed_response(self.challenge, self.rig, self.authority, "rig")
        raw = response_envelope(self.challenge, response, 1000)
        self.replies = [(200, b"[" + raw + b"," + raw + b"]")]
        with self.assertRaises(ChallengeError):
            client.read_peer_response(self.challenge, self.rig.public_key_der)

    def test_token_lookup_uses_exact_v3_record(self):
        response = signed_response(self.challenge, self.rig, self.authority, "rig")
        self.replies = [(200, response_envelope(self.challenge, response, 1000))]
        result = self.client(self.phone, "phone", token=True).read_peer_response(self.challenge, self.rig.public_key_der)
        self.assertEqual(result, response)
        self.assertTrue(self.calls[-1][1].startswith("/api/v3/devicestatus/"))
        self.assertIsNone(self.calls[-1][2]["query"])

    def test_absent_redirect_and_denied_do_not_admit_or_retry(self):
        client = self.client(self.phone, "phone")
        self.replies = [(404, b"")]
        self.assertIsNone(client.read_peer_response(self.challenge, self.rig.public_key_der))
        for status in (302, 401, 403, 410, 500):
            before = len(self.calls)
            self.replies = [(status, b"{}")]
            with self.assertRaises(NightscoutAuthorizationError):
                client.read_peer_response(self.challenge, self.rig.public_key_der)
            self.assertEqual(len(self.calls), before + 1)

    def test_context_mismatch_fails_before_network(self):
        client = self.client(self.phone, "phone")
        moved = dict(self.challenge, authority_context_id="ns_" + "a" * 64)
        with self.assertRaises(ChallengeError):
            client.read_peer_response(moved, self.rig.public_key_der)
        with self.assertRaises(ChallengeError):
            self.client(self.rig, "rig").read_peer_response(self.challenge, self.phone.public_key_der)
        self.assertEqual(self.calls, [])

    def test_invalidated_or_expired_network_result_fails_closed(self):
        for invalidate in (True, False):
            self.time = 0
            client = self.client(self.phone, "phone")
            def late():
                if invalidate:
                    client.invalidate()
                else:
                    self.time = 60
                return 404, b""
            self.replies = [late]
            with self.assertRaises(ChallengeError):
                client.read_peer_response(self.challenge, self.rig.public_key_der)

    def test_busy_client_and_unsafe_configuration(self):
        client = self.client(self.phone, "phone")
        client._operation.acquire()
        try:
            with self.assertRaises(ChallengeError):
                client.read_peer_response(self.challenge, self.rig.public_key_der)
        finally:
            client._operation.release()
        for url in ("http://example.invalid", "https://placeholder@example.invalid"):
            with self.assertRaises(NightscoutAuthorizationError):
                NightscoutWriteProofClient(url, self.phone, "phone", api_secret="synthetic", transport=self.transport)
        self.assertEqual(self.calls, [])

    def test_successful_publication_is_not_repeated_or_rebound(self):
        client = self.client(self.rig, "rig")
        self.replies = [(200, b'{"serverTimeEpoch":1000}'), (201, b"{}")]
        identifier = client.publish_own_response(self.challenge)
        self.assertEqual(client.publish_own_response(self.challenge), identifier)
        self.assertEqual(len(self.calls), 2)
        moved = dict(self.challenge, verifier_credential_id="d" * 64)
        with self.assertRaises(ChallengeError):
            client.publish_own_response(moved)
        self.assertEqual(len(self.calls), 2)

    def test_ambiguous_publication_cannot_be_retried(self):
        client = self.client(self.rig, "rig")
        def failed_write():
            raise NightscoutAuthorizationError("network")
        self.replies = [(200, b'{"serverTimeEpoch":1000}'), failed_write]
        with self.assertRaises(NightscoutAuthorizationError):
            client.publish_own_response(self.challenge)
        with self.assertRaises(ChallengeError):
            client.publish_own_response(self.challenge)
        self.assertEqual(len(self.calls), 2)

    def test_shared_rate_budget_refills_without_unbounded_pending_jobs(self):
        client = self.client(self.phone, "phone")
        self.replies = [(404, b"")] * 7
        for _ in range(6):
            self.assertIsNone(client.read_peer_response(self.challenge, self.rig.public_key_der))
        with self.assertRaises(ChallengeError):
            client.read_peer_response(self.challenge, self.rig.public_key_der)
        self.assertEqual(len(self.calls), 6)
        self.time = 10
        self.assertIsNone(client.read_peer_response(self.challenge, self.rig.public_key_der))
        self.assertEqual(len(self.calls), 7)

    def test_clock_regression_between_jobs_irreversibly_invalidates(self):
        client = self.client(self.phone, "phone")
        self.time = 10
        self.replies = [(404, b"")]
        client.read_peer_response(self.challenge, self.rig.public_key_der)
        self.time = 9
        with self.assertRaises(ChallengeError):
            client.read_peer_response(self.challenge, self.rig.public_key_der)
        self.time = 20
        with self.assertRaises(ChallengeError):
            client.read_peer_response(self.challenge, self.rig.public_key_der)
        self.assertEqual(len(self.calls), 1)

    def test_fresh_readback_consumes_local_nonce_after_absent_poll(self):
        self.time = 3
        client = self.client(self.phone, "phone")
        challenge = client.issue_challenge(self.rig.credential_id, "rig")
        response = signed_response(challenge, self.rig, self.authority, "rig")
        self.replies = [(404, b""), (200, b"[" + response_envelope(challenge, response, 1000) + b"]")]
        self.time = 10
        self.assertIsNone(client.read_fresh_peer_response(challenge["nonce"], self.rig.public_key_der))
        self.time = 20
        self.assertEqual(client.issue_challenge(self.rig.credential_id, "rig"), challenge)
        fresh = client.read_fresh_peer_response(challenge["nonce"], self.rig.public_key_der)
        self.assertEqual(fresh.issued_at, 3)
        self.assertEqual(fresh.verified_at, 20)
        self.assertEqual(fresh.owner_generation, client._owner_generation)
        self.assertNotEqual(fresh.owner_generation, self.client(self.phone, "phone")._owner_generation)
        self.assertEqual(fresh.response, response)
        self.assertEqual(fresh.challenge, challenge)
        client.validate_current_readback(fresh)
        replacement = self.client(self.phone, "phone")
        with self.assertRaises(ChallengeError):
            replacement.validate_current_readback(fresh)
        self.time = 123
        with self.assertRaises(ChallengeError):
            client.validate_current_readback(fresh)
        client.invalidate()
        with self.assertRaises(ChallengeError):
            client.validate_current_readback(fresh)
        for nonce in (challenge["nonce"], "0" * 64):
            with self.assertRaises(ChallengeError):
                client.read_fresh_peer_response(nonce, self.rig.public_key_der)
        self.assertEqual(len(self.calls), 2)

    def test_clock_change_after_consumption_cannot_return_receipt(self):
        for terminal_time in (120, -1):
            self.time = 0
            client = self.client(self.phone, "phone")
            challenge = client.issue_challenge(self.rig.credential_id, "rig")
            response = signed_response(challenge, self.rig, self.authority, "rig")
            self.replies = [(200, b"[" + response_envelope(challenge, response, 1000) + b"]")]
            consume = client._pending.consume_with_interval
            def shifted(nonce):
                result = consume(nonce)
                self.time = terminal_time
                return result
            client._pending.consume_with_interval = shifted
            with self.assertRaises(ChallengeError):
                client.read_fresh_peer_response(challenge["nonce"], self.rig.public_key_der)
            self.time = 1
            with self.assertRaises(ChallengeError):
                client.read_fresh_peer_response(challenge["nonce"], self.rig.public_key_der)
            if terminal_time == -1:
                with self.assertRaises(ChallengeError):
                    client.issue_challenge(self.rig.credential_id, "rig")

    def test_expiry_during_network_readback_cannot_produce_fresh_result(self):
        client = self.client(self.phone, "phone")
        challenge = client.issue_challenge(self.rig.credential_id, "rig")
        response = signed_response(challenge, self.rig, self.authority, "rig")
        def late():
            self.time = 121
            return 200, b"[" + response_envelope(challenge, response, 1000) + b"]"
        self.replies = [late]
        self.time = 119
        with self.assertRaises(ChallengeError):
            client.read_fresh_peer_response(challenge["nonce"], self.rig.public_key_der)
        self.assertEqual(len(self.calls), 1)

    def test_cancelled_or_malformed_readback_nonce_is_not_retried(self):
        client = self.client(self.phone, "phone")
        first = client.issue_challenge(self.rig.credential_id, "rig")
        client.cancel_challenge(first["nonce"])
        with self.assertRaises(ChallengeError):
            client.read_fresh_peer_response(first["nonce"], self.rig.public_key_der)
        self.assertEqual(len(self.calls), 0)
        second = client.issue_challenge(self.rig.credential_id, "rig")
        self.replies = [(200, b"[{}]")]
        for _ in range(2):
            with self.assertRaises(ChallengeError):
                client.read_fresh_peer_response(second["nonce"], self.rig.public_key_der)
        self.assertEqual(len(self.calls), 1)

    def test_invalidation_during_fresh_readback_discards_pending_state(self):
        client = self.client(self.phone, "phone")
        challenge = client.issue_challenge(self.rig.credential_id, "rig")
        def invalidated():
            client.invalidate()
            return 404, b""
        self.replies = [invalidated]
        with self.assertRaises(ChallengeError):
            client.read_fresh_peer_response(challenge["nonce"], self.rig.public_key_der)
        with self.assertRaises(ChallengeError):
            client.issue_challenge(self.rig.credential_id, "rig")


class JoinedProofWorkflowTests(unittest.TestCase):
    """Two production clients; synthetic store, not deployment-policy evidence."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="openaps-joined-proof-")
        self.addCleanup(self.directory.cleanup)
        self.url = "https://example.invalid/base"
        self.authority = proof_authority_context_id(self.url)
        self.time = 0.0
        self.records = {}
        self.calls = []
        self.allowed = {"phone-synthetic", "rig-synthetic"}
        test = self
        class Store:
            def request_bytes(self, method, path, body=None, query=None, api_secret=None, **kwargs):
                test.calls.append((api_secret, method, path))
                if api_secret not in test.allowed:
                    return 401, b"{}"
                if method == "GET" and path == "/api/v1/status.json":
                    return 200, b'{"serverTimeEpoch":1000}'
                if method == "POST" and path == "/api/v1/devicestatus/":
                    # Copy through JSON so neither client shares mutable records.
                    test.records.setdefault(body["identifier"], []).append(json.loads(json.dumps(body)))
                    return 200, b"{}"
                if method == "GET" and path == "/api/v1/devicestatus.json":
                    rows = test.records.get(query["find[identifier]"], [])[:int(query["count"])]
                    return 200, json.dumps(rows).encode("utf-8")
                raise AssertionError("unexpected proof route")
        self.store = Store()
        self.identities = {kind: DeviceIdentity(os.path.join(self.directory.name, kind)) for kind in ("phone", "rig")}
        self.clients = {kind: NightscoutWriteProofClient(self.url, self.identities[kind], kind,
            api_secret=kind + "-synthetic", transport=self.store, clock=lambda: self.time) for kind in ("phone", "rig")}

    def test_mutual_workflow_requires_each_own_publication_and_independent_read(self):
        for verifier, peer in (("phone", "rig"), ("rig", "phone")):
            owner, responder = self.clients[verifier], self.clients[peer]
            key = self.identities[peer].public_key_der
            challenge = owner.issue_challenge(self.identities[peer].credential_id, peer)
            # A direct, correctly signed response cannot populate the verifier's
            # NS store. The reader accepts only its independent store lookup.
            signed_response(challenge, self.identities[peer], self.authority, peer)
            self.assertIsNone(owner.read_fresh_peer_response(challenge["nonce"], key))
            before = len(self.calls)
            with self.assertRaises(ChallengeError):
                owner.publish_own_response(challenge)  # No confused-deputy write.
            self.assertEqual(len(self.calls), before)
            identifier = responder.publish_own_response(challenge)
            fresh = owner.read_fresh_peer_response(challenge["nonce"], key)
            self.assertEqual(fresh.challenge, challenge)
            self.assertEqual(self.records[identifier][0]["openaps_write_response"], fresh.response)
            self.assertEqual(self.calls[-1][0], verifier + "-synthetic")
            with self.assertRaises(ChallengeError):
                owner.read_fresh_peer_response(challenge["nonce"], key)
        self.assertEqual(sum(len(rows) for rows in self.records.values()), 2)
        self.assertTrue(all(not os.path.exists(identity.peer_directory) for identity in self.identities.values()))

    def test_denied_responder_cannot_turn_direct_signature_into_readback(self):
        owner, peer = self.clients["phone"], self.clients["rig"]
        challenge = owner.issue_challenge(self.identities["rig"].credential_id, "rig")
        self.allowed.remove("rig-synthetic")
        with self.assertRaises(NightscoutAuthorizationError):
            peer.publish_own_response(challenge)
        self.assertEqual(self.records, {})
        self.assertIsNone(owner.read_fresh_peer_response(challenge["nonce"], self.identities["rig"].public_key_der))

    def test_historical_row_and_other_authority_cannot_satisfy_new_challenge(self):
        owner, peer = self.clients["phone"], self.clients["rig"]
        old = owner.issue_challenge(self.identities["rig"].credential_id, "rig")
        peer.publish_own_response(old)
        owner.cancel_challenge(old["nonce"])
        fresh = owner.issue_challenge(self.identities["rig"].credential_id, "rig")
        self.assertNotEqual(old["nonce"], fresh["nonce"])
        self.assertIsNone(owner.read_fresh_peer_response(fresh["nonce"], self.identities["rig"].public_key_der))
        moved = dict(fresh, authority_context_id=proof_authority_context_id("https://other.invalid"))
        before = len(self.calls)
        with self.assertRaises(ChallengeError):
            peer.publish_own_response(moved)
        self.assertEqual(len(self.calls), before)


if __name__ == "__main__":
    unittest.main()
