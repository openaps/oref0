import os
import tempfile
import unittest
import concurrent.futures
import json
from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.write_challenge import (SCHEMA, RESPONSE_SCHEMA, ChallengeError, fresh_challenge,
    validate_challenge, signing_bytes, signed_response, verify_response_signature, PendingChallenges,
    response_envelope, decode_response_envelope, response_identifier)


class WriteChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="openaps-write-proof-test-")
        cls.phone = DeviceIdentity(os.path.join(cls.directory.name, "phone"))
        cls.rig = DeviceIdentity(os.path.join(cls.directory.name, "rig"))
        cls.authority = "ns_" + "a" * 64

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def challenge(self):
        return fresh_challenge(self.authority, self.phone.credential_id, "phone", self.rig.credential_id, "rig")

    def test_fresh_nonce_and_canonical_domain(self):
        value = self.challenge()
        self.assertNotEqual(value["nonce"], self.challenge()["nonce"])
        value["nonce"] = "0" * 64
        self.assertEqual(signing_bytes(value), "\x00".join([RESPONSE_SCHEMA, self.authority,
            self.phone.credential_id, "phone", self.rig.credential_id, "rig", "0" * 64]).encode("ascii"))

    def test_offline_signature_only_without_peer_cache_mutation(self):
        value = self.challenge()
        response = signed_response(value, self.rig, self.authority, "rig")
        before = sorted(os.listdir(self.phone.peer_directory)) if os.path.isdir(self.phone.peer_directory) else []
        verify_response_signature(value, response, self.rig.public_key_der, self.phone)
        after = sorted(os.listdir(self.phone.peer_directory)) if os.path.isdir(self.phone.peer_directory) else []
        self.assertEqual(before, after)

    def test_responder_rejects_wrong_authority_key_and_role(self):
        value = self.challenge()
        for identity, authority, kind in ((self.phone, self.authority, "rig"),
                (self.rig, "ns_" + "b" * 64, "rig"), (self.rig, self.authority, "phone")):
            with self.assertRaises(ChallengeError):
                signed_response(value, identity, authority, kind)

    def test_response_cannot_move_to_another_challenge(self):
        value = self.challenge()
        response = signed_response(value, self.rig, self.authority, "rig")
        with self.assertRaises(ChallengeError):
            verify_response_signature(self.challenge(), response, self.rig.public_key_der, self.phone)
        value["verifier_credential_id"] = "b" * 64
        response["verifier_credential_id"] = "b" * 64
        with self.assertRaises(ChallengeError):
            verify_response_signature(value, response, self.rig.public_key_der, self.phone)

    def test_malformed_fields_and_metadata_rejected(self):
        for name, replacement in (("nonce", "short"), ("nonce", "F" * 64),
                ("peer_device_kind", "phone"), ("authority_context_id", "other"), ("subject", "synthetic")):
            value = self.challenge()
            value[name] = replacement
            with self.assertRaises(ChallengeError):
                validate_challenge(value)
        value = self.challenge()
        response = signed_response(value, self.rig, self.authority, "rig")
        response["subject"] = "synthetic"
        with self.assertRaises(ChallengeError):
            verify_response_signature(value, response, self.rig.public_key_der, self.phone)

    def test_wrong_key_and_noncanonical_signature_encoding_rejected(self):
        value = self.challenge()
        response = signed_response(value, self.rig, self.authority, "rig")
        with self.assertRaises(ChallengeError):
            verify_response_signature(value, response, self.phone.public_key_der, self.phone)
        with self.assertRaises(ChallengeError):
            verify_response_signature(value, response, b"x" * 92, self.phone)
        response["signature"] += "\n"
        with self.assertRaises(ChallengeError):
            verify_response_signature(value, response, self.rig.public_key_der, self.phone)

    def test_envelope_roundtrip_with_unsigned_server_metadata(self):
        challenge = self.challenge()
        response = signed_response(challenge, self.rig, self.authority, "rig")
        data = response_envelope(challenge, response, 1000)
        self.assertEqual(decode_response_envelope(data, challenge), response)
        record = json.loads(data.decode("utf-8"))
        record.update({"subject": "unproven", "srvCreated": 1000, "created_at": "unproven"})
        wrapped = json.dumps({"result": record}).encode("utf-8")
        self.assertEqual(decode_response_envelope(wrapped, challenge), response)
        record["utcOffset"] = -420
        self.assertEqual(decode_response_envelope(json.dumps({"result": record}).encode("utf-8"), challenge), response)
        self.assertEqual(record["identifier"], response_identifier(challenge))

    def test_envelope_rejects_binding_and_inner_metadata_changes(self):
        challenge = self.challenge()
        response = signed_response(challenge, self.rig, self.authority, "rig")
        record = json.loads(response_envelope(challenge, response, 1000).decode("utf-8"))
        for key, value in (("identifier", "wrong"), ("app", "wrong"), ("device", "wrong"),
                ("date", True), ("date", 0), ("utcOffset", False), ("utcOffset", 1441)):
            changed = dict(record)
            changed[key] = value
            with self.assertRaises(ChallengeError):
                decode_response_envelope(json.dumps(changed).encode("utf-8"), challenge)
        response["subject"] = "unproven"
        with self.assertRaises(ChallengeError):
            response_envelope(challenge, response, 1000)

    def test_envelope_parser_bounds_duplicates_and_nonobjects(self):
        challenge = self.challenge()
        for data in (b"x" * 8193, b'{"a":1,"a":2}', b'{"a":1,"\\u0061":2}',
                b"[" * 9 + b"0" + b"]" * 9, b"[]", b'{"result":[]}', b'{"a":NaN}', b"\xff"):
            with self.assertRaises(ChallengeError):
                decode_response_envelope(data, challenge)

    def test_envelope_shape_alone_is_not_signature_verification(self):
        challenge = self.challenge()
        response = signed_response(challenge, self.rig, self.authority, "rig")
        other = self.challenge()
        # Well-shaped signature from a different nonce must still fail crypto.
        response["signature"] = signed_response(other, self.rig, self.authority, "rig")["signature"]
        decoded = decode_response_envelope(response_envelope(challenge, response, 1000), challenge)
        with self.assertRaises(ChallengeError):
            verify_response_signature(challenge, decoded, self.rig.public_key_der, self.phone)


class PendingChallengeTests(unittest.TestCase):
    def setUp(self):
        self.time = 0.0
        self.ledger = PendingChallenges("ns_" + "a" * 64, "b" * 64, "rig", clock=lambda: self.time)

    def issue(self, digit="c"):
        return self.ledger.issue(digit * 64, "phone")

    def test_reuse_expiry_and_single_attempt(self):
        first = self.issue()
        self.time = 119
        self.assertEqual(first, self.issue())
        self.time = 120
        with self.assertRaises(ChallengeError):
            self.ledger.take_for_signature_verification(first["nonce"])
        fresh = self.issue()
        self.assertEqual(fresh, self.ledger.take_for_signature_verification(fresh["nonce"]))
        with self.assertRaises(ChallengeError):
            self.ledger.take_for_signature_verification(fresh["nonce"])

    def test_capacity_cancel_rate_and_refill(self):
        entries = [self.issue(str(i)) for i in range(4)]
        with self.assertRaises(ChallengeError):
            self.issue()
        for entry in entries:
            self.ledger.cancel(entry["nonce"])
        for _ in range(2):
            self.ledger.cancel(self.issue()["nonce"])
        with self.assertRaises(ChallengeError):
            self.issue()
        self.time = 10
        self.issue()

    def test_invalidation_regression_restart_and_context(self):
        first = self.issue()
        with self.assertRaises(ChallengeError):
            self.ledger.issue("c" * 64, "rig")
        self.time = -1
        with self.assertRaises(ChallengeError):
            self.ledger.take_for_signature_verification(first["nonce"])
        self.time = 20
        with self.assertRaises(ChallengeError):
            self.issue()
        new = PendingChallenges("ns_" + "a" * 64, "b" * 64, "rig", clock=lambda: self.time)
        with self.assertRaises(ChallengeError):
            new.take_for_signature_verification(first["nonce"])
        new.invalidate()
        with self.assertRaises(ChallengeError):
            new.issue("c" * 64, "phone")

    def test_collision_and_bad_entropy(self):
        ledger = PendingChallenges("ns_" + "a" * 64, "b" * 64, "rig",
            clock=lambda: 0, nonce=lambda: "0" * 64)
        ledger.issue("c" * 64, "phone")
        with self.assertRaises(ChallengeError):
            ledger.issue("d" * 64, "phone")
        malformed = PendingChallenges("ns_" + "a" * 64, "b" * 64, "rig",
            clock=lambda: 0, nonce=lambda: "short")
        with self.assertRaises(ChallengeError):
            malformed.issue("c" * 64, "phone")

    def test_returned_fields_do_not_mutate_pending(self):
        value = self.issue()
        value["peer_credential_id"] = "d" * 64
        self.assertEqual(self.issue()["peer_credential_id"], "c" * 64)

    def test_concurrent_consumption_has_one_winner(self):
        nonce = self.issue()["nonce"]
        def take(_):
            try:
                self.ledger.take_for_signature_verification(nonce)
                return 1
            except ChallengeError:
                return 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            self.assertEqual(sum(executor.map(take, range(32))), 1)


if __name__ == "__main__":
    unittest.main()
