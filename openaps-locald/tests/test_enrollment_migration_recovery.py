import base64
import copy
import unittest
from types import SimpleNamespace

from openaps_locald.nightscout_authorization import (
    NightscoutDeviceAuthorizationClient, NightscoutAuthorizationError,
)


class MigrationRecoveryTests(unittest.TestCase):
    def make_client(self):
        client = NightscoutDeviceAuthorizationClient.__new__(NightscoutDeviceAuthorizationClient)
        client.base_url = "https://example.invalid"
        client.api_secret = None
        client.authority_context_id = "ns_" + "a" * 64
        client.device_kind = "rig"
        self.signed = []
        client.identity = SimpleNamespace(credential_id="b" * 64,
            sign=lambda transcript: self.signed.append(transcript) or b"synthetic-proof")
        client.jwt = SimpleNamespace(subject="synthetic-subject")
        client.status = lambda: {"srvDate": 1000000}
        self.challenge = {
            "schema": "openaps.enrollment-recovery.v1",
            "challenge_id": "11111111-2222-4333-8444-555555555555",
            "nonce": base64.b64encode(b"x" * 32).decode("ascii"),
            "authority_context_id": client.authority_context_id,
            "subject": client.jwt.subject, "registry_digest": "c" * 64,
            "expires_at": 1120000,
        }
        self.requests = []
        self.response = {"status": "recovered", "reenroll_required": True}
        def request(method, path, body=None):
            self.requests.append((method, path, body))
            return 200, copy.deepcopy(self.challenge if path.endswith("challenge") else self.response)
        client._authenticated_request = request
        return client

    def test_signs_bound_transcript_without_delete(self):
        client = self.make_client()
        client._recover_migrated_self_enrollment()
        self.assertEqual([r[0] for r in self.requests], ["POST", "POST"])
        expected = "\n".join([self.challenge["schema"], self.challenge["challenge_id"],
            client.identity.credential_id, "rig", client.authority_context_id,
            "synthetic-subject", self.challenge["nonce"], "c" * 64, "1120000"])
        self.assertEqual(self.signed, [expected.encode("utf-8")])

    def test_already_current_is_idempotent(self):
        client = self.make_client()
        self.response = {"status": "already_current", "reenroll_required": False}
        client._recover_migrated_self_enrollment()

    def test_rejects_unbound_or_expired_challenge_before_signing(self):
        for key, value in [("subject", "foreign-subject"), ("authority_context_id", "ns_" + "d" * 64),
                           ("expires_at", 1000000), ("expires_at", 1120001),
                           ("expires_at", True), ("nonce", "eA=="),
                           ("registry_digest", "C" * 64), ("challenge_id", "invalid")]:
            with self.subTest(key=key, value=value):
                client = self.make_client()
                self.challenge[key] = value
                with self.assertRaises(NightscoutAuthorizationError):
                    client._recover_migrated_self_enrollment()
                self.assertEqual(self.signed, [])
                self.assertEqual(len(self.requests), 1)

    def test_never_uses_legacy_secret_or_plain_http(self):
        for secret, url in [("synthetic-secret", "https://example.invalid"),
                            (None, "http://example.invalid")]:
            client = self.make_client()
            client.api_secret, client.base_url = secret, url
            with self.assertRaises(NightscoutAuthorizationError):
                client._recover_migrated_self_enrollment()
            self.assertEqual(self.requests, [])

    def test_rejects_inconsistent_completion(self):
        client = self.make_client()
        self.response = {"status": "recovered", "reenroll_required": False}
        with self.assertRaises(NightscoutAuthorizationError):
            client._recover_migrated_self_enrollment()

    def test_missing_endpoint_never_sends_completion(self):
        client = self.make_client()
        client._authenticated_request = lambda *args, **kwargs: (404, {})
        self.assertFalse(client._recover_migrated_self_enrollment())
        self.assertEqual(self.signed, [])


if __name__ == "__main__":
    unittest.main()
