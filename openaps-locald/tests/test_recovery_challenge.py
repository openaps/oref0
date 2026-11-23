import json
import os
import tempfile
import unittest
import uuid

from openaps_locald.device_identity import DeviceIdentity
from openaps_locald.write_challenge import ChallengeError
from openaps_locald import recovery_challenge as recovery
from openaps_locald.continuity import Continuity, BoundContinuity, ContinuityError


class RecoveryChallengeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="openaps-recovery-test-")
        self.addCleanup(directory.cleanup)
        self.phone = DeviceIdentity(os.path.join(directory.name, "phone"))
        self.rig = DeviceIdentity(os.path.join(directory.name, "rig"))
        self.authority = "ns_" + "a" * 64
        self.request = recovery.fresh_request(self.authority, self.phone.credential_id,
            "phone", self.rig.credential_id, "rig", uuid.uuid4())

    def verify(self, response):
        return recovery.verify_response(self.request, response, self.rig.public_key_der, self.phone)

    def test_roundtrip_and_signed_field_binding(self):
        response = recovery.signed_response(self.request, self.rig, self.authority, "rig", 0.0001)
        self.assertEqual(self.verify(response), 0.001)
        self.assertEqual(recovery.decode_request(recovery.encode_request(self.request)), self.request)
        self.assertEqual(recovery.verify_response_data(self.request, json.dumps(response).encode("ascii"),
            self.rig.public_key_der, self.phone), 0.001)
        for name in response:
            with self.assertRaises(ChallengeError):
                self.verify(dict(response, **{name: "substituted"}))
        with self.assertRaises(ChallengeError):
            self.verify(dict(response, contact_age_ms="2"))
        self.assertFalse(os.path.exists(self.phone.peer_directory))

    def test_boundaries_and_wrong_signer(self):
        for age in (-1, float("nan"), float("inf"), 86400, 86399.9999):
            with self.assertRaises(ChallengeError):
                recovery.signed_response(self.request, self.rig, self.authority, "rig", age)
        for identity, authority, kind in ((self.phone, self.authority, "rig"),
                (self.rig, "ns_" + "b" * 64, "rig"), (self.rig, self.authority, "phone")):
            with self.assertRaises(ChallengeError):
                recovery.signed_response(self.request, identity, authority, kind, 1)

    def test_bounded_duplicate_aware_decoding(self):
        data = recovery.encode_request(self.request)
        for malformed in (b"", b" " * 4097, b"[]", b'{"nested":{}}', data[:-1],
                b'{"schema":"duplicate",' + data[1:]):
            with self.assertRaises(ChallengeError):
                recovery.decode_request(malformed)
            with self.assertRaises(ChallengeError):
                recovery.verify_response_data(self.request, malformed, self.rig.public_key_der, self.phone)

    def test_scoped_witness_requires_independent_exact_peer_contact(self):
        binding = (self.authority, self.rig.credential_id, self.phone.credential_id, "connection", "generation")
        for mode in ("valid", "recovered", "expired", "invalidated", "other-peer"):
            now = [0]
            state = Continuity(clock=lambda: now[0], recovered_age=10 if mode == "recovered" else None)
            owner = BoundContinuity(state, binding)
            now[0] = 86400 if mode == "expired" else 100
            if mode == "invalidated":
                owner.invalidate()
            request = dict(self.request)
            if mode == "other-peer":
                request["requester_credential_id"] = "b" * 64
            if mode == "valid":
                response = owner.witness_response(request, self.rig, binding)
                self.assertEqual(self.verify(response), 100)
                now[0] = 86400
                with self.assertRaises(ContinuityError):
                    owner.witness_response(request, self.rig, binding)
            else:
                with self.assertRaises(ContinuityError):
                    owner.witness_response(request, self.rig, binding)
