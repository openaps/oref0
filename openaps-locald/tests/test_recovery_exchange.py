import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.write_challenge import ChallengeError
from openaps_locald.recovery_exchange import RecoveryExchange
from openaps_locald import recovery_challenge as codec


class RecoveryExchangeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="openaps-recovery-exchange-")
        self.addCleanup(directory.cleanup)
        self.phone = DeviceIdentity(os.path.join(directory.name, "phone"))
        self.rig = DeviceIdentity(os.path.join(directory.name, "rig"))
        self.authority = "ns_" + "a" * 64
        self.now = 10.0

    def exchange(self):
        return RecoveryExchange(self.authority, self.phone.credential_id, "phone",
            self.rig.credential_id, "rig", self.rig.public_key_der, uuid.uuid4(),
            self.phone, clock=lambda: self.now)

    def response(self, exchange, age=100):
        request = codec.decode_request(exchange.request_data())
        return json.dumps(codec.signed_response(request, self.rig, self.authority, "rig", age)).encode("ascii")

    def test_one_use_delay_and_failure_boundaries(self):
        for mode in ("success", "expired", "gap", "cancelled", "malformed", "regressed", "nonfinite"):
            self.now = 10.0
            exchange = self.exchange()
            response = self.response(exchange, 86399 if mode == "gap" else 100)
            self.now = {"expired": 30, "regressed": 9, "nonfinite": float("nan")}.get(mode, 12)
            if mode == "cancelled":
                exchange.cancel()
            if mode == "success":
                evidence = exchange.consume(response)
                self.assertEqual(evidence.contact_age_upper_bound, 102)
                self.assertEqual(evidence.signed_response, response)
                self.assertEqual(evidence.witness_public_key_der, self.rig.public_key_der)
                self.assertIsInstance(evidence.signed_response, bytes)
                self.assertEqual(codec.verify_response_data(dict(evidence.request),
                    evidence.signed_response, evidence.witness_public_key_der, self.phone), 100)
                with self.assertRaises(AttributeError):
                    evidence.signed_response = b"changed"
                with self.assertRaises(ChallengeError):
                    exchange.current_contact_age(type(evidence)(*evidence))
                with self.assertRaises(TypeError):
                    evidence.request["nonce"] = "0" * 64
            else:
                with self.assertRaises(ChallengeError):
                    exchange.consume(b"" if mode == "malformed" else response)
            with self.assertRaises(ChallengeError):
                exchange.consume(response)
            with self.assertRaises(ChallengeError):
                exchange.request_data()

    def test_cancellation_and_expiry_during_verification(self):
        for mode in ("cancelled", "expired"):
            self.now = 10
            exchange = self.exchange()
            response = self.response(exchange)
            original = codec.verify_response_data
            def verifying(*args):
                if mode == "cancelled":
                    exchange.cancel()
                else:
                    self.now = 30
                return original(*args)
            with patch.object(codec, "verify_response_data", side_effect=verifying):
                with self.assertRaises(ChallengeError):
                    exchange.consume(response)

    def test_contention_does_not_queue_work(self):
        exchange = self.exchange()
        exchange._lock.acquire()
        try:
            with self.assertRaises(ChallengeError):
                exchange.request_data()
            with self.assertRaises(ChallengeError):
                exchange.consume(b"")
            exchange.cancel()
        finally:
            exchange._lock.release()
        with self.assertRaises(ChallengeError):
            exchange.request_data()

    def test_preparation_delay_foreign_evidence_and_terminal_recheck(self):
        for mode in ("cancelled", "deadline", "gap"):
            self.now = 10
            exchange, foreign = self.exchange(), self.exchange()
            response = self.response(exchange, 86395 if mode == "gap" else 100)
            self.now = 12
            evidence = exchange.consume(response)
            self.now = 14
            self.assertEqual(exchange.current_contact_age(evidence), 86399 if mode == "gap" else 104)
            for invalid in (None, evidence._replace(), evidence):
                with self.assertRaises(ChallengeError):
                    foreign.current_contact_age(invalid)
            with self.assertRaises(ChallengeError):
                exchange.current_contact_age(evidence._replace())
            if mode == "cancelled":
                exchange.cancel()
            else:
                self.now = 30 if mode == "deadline" else 15
            with self.assertRaises(ChallengeError):
                exchange.current_contact_age(evidence)
