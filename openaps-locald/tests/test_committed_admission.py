import base64
import json
import unittest
import uuid

from openaps_locald import committed_admission as module
from openaps_locald.admission_candidate_archive import CandidateArchive
from openaps_locald.write_challenge import ChallengeError
from tests import test_admission_record


class CommittedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = test_admission_record.AdmissionRecordTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.context = self.f.context
        self.identity = self.f.fixture.phone
        self.candidate = self.f.prepare()
        self.audit = module.prepare(self.candidate, self.context, self.identity)

    def test_roundtrip_is_only_audit_and_candidate_schema_rejected(self):
        archive = module.CommittedArchive().inserting(self.audit, self.context, self.identity)
        restored = module.CommittedArchive(archive.encoded()).record(self.context, self.identity)
        self.assertEqual(restored.commit_id, self.candidate.commit_id)
        self.assertEqual(restored.candidate.proof.response, self.candidate.proof.response)
        self.assertFalse(hasattr(restored, "continuity"))
        self.assertFalse(hasattr(restored, "snapshot"))
        with self.assertRaises(ChallengeError):
            module.decode(self.candidate.encoded, self.context, self.identity)
        candidate_archive = CandidateArchive().inserting(self.candidate, self.identity)
        with self.assertRaises(ChallengeError):
            module.CommittedArchive(candidate_archive.encoded())

    def test_all_expected_scope_fields_and_exact_verifier_key(self):
        for name in self.context._fields:
            value = getattr(self.context, name)
            replacement = uuid.uuid4() if isinstance(value, uuid.UUID) else "wrong"
            with self.assertRaises((ChallengeError, ValueError)):
                module.decode(self.audit.encoded, self.context._replace(**{name: replacement}), self.identity)
        with self.assertRaises(ChallengeError):
            module.decode(self.audit.encoded, self.context, self.f.fixture.rig)

    def test_digest_commit_and_candidate_signature_revalidated(self):
        obj = json.loads(self.audit.encoded.decode())
        for name, value in (("candidate_sha256", "0" * 64), ("commit_id", str(uuid.uuid4())),
                            ("candidate", base64.b64encode(b"{}").decode())):
            changed = dict(obj, **{name: value})
            with self.assertRaises(ChallengeError):
                module.decode(module._json(changed), self.context, self.identity)
        # Recomputed outer digest still cannot authorize a changed signed proof.
        candidate = json.loads(self.candidate.encoded.decode())
        proof = json.loads(base64.b64decode(candidate["proof"]).decode())
        proof["response"]["signature"] = "invalid"
        candidate["proof"] = base64.b64encode(module._json(proof)).decode()
        raw = module._json(candidate)
        changed = dict(obj, candidate=base64.b64encode(raw).decode(),
                       candidate_sha256=module.hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ChallengeError):
            module.decode(module._json(changed), self.context, self.identity)

    def test_record_and_archive_strict_bounds(self):
        for data in (b"", self.audit.encoded + b" ", self.audit.encoded[:-1],
                     b"x" * (module.MAX_RECORD_BYTES + 1),
                     b'{"schema":"duplicate",' + self.audit.encoded[1:]):
            with self.assertRaises(ChallengeError):
                module.decode(data, self.context, self.identity)
        for data in (b"x" * (module.MAX_BYTES + 1), b'{"schema":"x","schema":"y"}',
                     module._json({"schema": module.ARCHIVE_SCHEMA, "records": {
                         format(i, "064x"): "eA==" for i in range(33)}}),
                     module._json({"schema": module.ARCHIVE_SCHEMA, "records": {
                         "a" * 64: base64.b64encode(b"x" * (module.MAX_RECORD_BYTES + 1)).decode()}})):
            with self.assertRaises(ChallengeError):
                module.CommittedArchive(data)
