import json
import unittest
import uuid
from unittest.mock import patch

from openaps_locald import committed_admission as committed, recovery_audit as audit, recovery_challenge as codec
from openaps_locald.recovery_exchange import RecoveryExchange
from openaps_locald.write_challenge import ChallengeError
from tests import test_committed_admission


class RecoveryAuditTests(unittest.TestCase):
    def setUp(self):
        self.f = test_committed_admission.CommittedAdmissionTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.now = 10.0
        c = self.f.context
        self.exchange = RecoveryExchange(c.authority, c.local_credential_id, c.local_kind,
            c.peer_credential_id, "rig", self.f.f.fixture.rig.public_key_der, uuid.uuid4(),
            self.f.identity, clock=lambda: self.now)
        request = codec.decode_request(self.exchange.request_data())
        response = codec.signed_response(request, self.f.f.fixture.rig, c.authority, "rig", 100)
        self.evidence = self.exchange.consume(json.dumps(response).encode("ascii"))

    def prepare(self, base=None, evidence=None):
        return committed.prepare_recovery(base or self.f.audit, self.f.context, self.f.identity,
            self.exchange, evidence or self.evidence)

    def test_roundtrip_revisions_preserve_base_and_do_not_restore_evidence(self):
        revised = self.prepare()
        self.assertEqual(revised.commit_id, self.f.audit.commit_id)
        self.assertEqual(revised.candidate.encoded, self.f.candidate.encoded)
        self.assertEqual(revised.recovery.age_before_write_ms, 100000)
        self.assertNotEqual(revised.recovery.recovery_commit_id, revised.commit_id)
        archive = committed.CommittedArchive().inserting(revised, self.f.context, self.f.identity)
        restored = committed.CommittedArchive(archive.encoded()).record(self.f.context, self.f.identity)
        self.assertEqual(restored.recovery, revised.recovery)
        second = self.prepare(revised)
        self.assertNotEqual(second.recovery.recovery_commit_id, revised.recovery.recovery_commit_id)
        self.assertEqual(second.commit_id, revised.commit_id)
        with self.assertRaises(ChallengeError):
            self.exchange.current_contact_age(restored.recovery)

    def test_foreign_evidence_and_expiry_rejected(self):
        with self.assertRaises(ChallengeError):
            self.prepare(evidence=self.evidence._replace())
        self.now = 30
        with self.assertRaises(ChallengeError):
            self.prepare()

    def test_verification_delay_is_included_in_historical_age(self):
        verify = codec.verify_response_data
        def delayed(*args):
            result = verify(*args)
            self.now += 0.25
            return result
        with patch.object(codec, "verify_response_data", side_effect=delayed):
            revised = self.prepare()
        self.assertEqual(revised.recovery.age_before_write_ms,
                         int(audit.math.ceil((100 + self.now - 10) * 1000)))

    def test_tampering_and_bounds(self):
        revised = self.prepare()
        obj = json.loads(revised.recovery.encoded.decode())
        for name, value in (("base_commit_id", str(uuid.uuid4())), ("candidate_sha256", "0" * 64),
                            ("age_before_write_ms", "99999"), ("age_before_write_ms", "0100000"),
                            ("age_before_write_ms", "86400000"), ("request", audit._b64(b"{}")),
                            ("witness_public_key_der", audit._b64(self.f.identity.public_key_der)),
                            ("recovery_commit_id", str(revised.commit_id))):
            with self.assertRaises(ChallengeError):
                audit.decode(audit._json(dict(obj, **{name: value})), revised.candidate, self.f.identity)
        for raw in (b"x" * (audit.MAX_BYTES + 1), revised.recovery.encoded + b" ",
                    b'{"schema":"duplicate",' + revised.recovery.encoded[1:]):
            with self.assertRaises(ChallengeError):
                audit.decode(raw, revised.candidate, self.f.identity)
