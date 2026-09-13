import tempfile
import unittest
import uuid
from unittest.mock import patch

from openaps_locald.admission_owner import AdmissionOwner, LiveAdmissionContext, _RecoveryRequired
from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.write_challenge import ChallengeError
from tests import test_admission_owner


class AdmissionRestoreTests(unittest.TestCase):
    def setUp(self):
        fixture = test_admission_owner.AdmissionOwnerTests()
        self.addCleanup(fixture.doCleanups)
        (self.f, self.client, self.before, self.receipt, self.after, self.policy,
         self.lease, self.context, self.candidates) = fixture.fixture()
        directory = tempfile.TemporaryDirectory(prefix="synthetic-committed-")
        self.addCleanup(directory.cleanup)
        self.storage = AdmissionStorage(directory.name)

    def owner(self, storage=None, context=None, validate=None):
        context = context or self.context
        return AdmissionOwner(self.client, self.candidates, context, self.f.rig,
            LiveAdmissionContext(context), self.lease, validate or (lambda expected: None),
            clock=lambda: self.f.time, committed_storage=storage or self.storage)

    def admit(self, owner):
        return owner.admit_fresh(self.receipt, self.before, self.after)

    def test_fresh_restart_restricted_handle_only_and_invalidation(self):
        first = self.owner()
        self.admit(first)
        first.snapshot(str(uuid.uuid4()))
        restored = self.owner()
        handle = restored.restore_recovery_required()
        self.assertIsNone(restored.require_recovery_handle(handle))
        with self.assertRaises(ChallengeError):
            restored.snapshot(str(uuid.uuid4()))
        with self.assertRaises(ChallengeError):
            first.require_recovery_handle(handle)
        with self.assertRaises(ChallengeError):
            _RecoveryRequired(None, restored, object(), handle._audit)
        self.admit(restored)
        with self.assertRaises(ChallengeError):
            restored.require_recovery_handle(handle)
        next_owner = self.owner()
        next_handle = next_owner.restore_recovery_required()
        next_owner.invalidate()
        with self.assertRaises(ChallengeError):
            next_owner.require_recovery_handle(next_handle)

    def test_missing_wrong_scope_and_candidate_only_rejected(self):
        with self.assertRaises(ChallengeError):
            self.owner().restore_recovery_required()
        self.admit(self.owner())
        with self.assertRaises(ChallengeError):
            self.owner(context=self.context._replace(settings_epoch=uuid.uuid4())).restore_recovery_required()
        self.storage.replace(self.candidates.load())
        with self.assertRaises(ChallengeError):
            self.owner().restore_recovery_required()

    def test_ambiguous_write_requires_new_owner_and_never_activates(self):
        real_replace = self.storage.replace
        def post_write(data, expecting):
            real_replace(data, expecting=expecting)
            raise OSError("synthetic post-write error")
        owner = self.owner()
        with patch.object(self.storage, "replace", side_effect=post_write):
            with self.assertRaises(OSError):
                self.admit(owner)
        with self.assertRaises(ChallengeError):
            owner.snapshot(str(uuid.uuid4()))
        with self.assertRaises(ChallengeError):
            owner.restore_recovery_required()
        restarted = self.owner()
        restarted.require_recovery_handle(restarted.restore_recovery_required())

    def test_failed_write_and_elapsed_original_deadline(self):
        owner = self.owner()
        with patch.object(self.storage, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.admit(owner)
        self.assertIsNone(self.storage.load())
        with self.assertRaises(ChallengeError):
            owner.snapshot(str(uuid.uuid4()))
        real_replace = self.storage.replace
        def delayed(data, expecting):
            real_replace(data, expecting=expecting)
            self.f.time += 120
        delayed_owner = self.owner()
        with patch.object(self.storage, "replace", side_effect=delayed):
            with self.assertRaises(ChallengeError):
                self.admit(delayed_owner)
        with self.assertRaises(ChallengeError):
            delayed_owner.snapshot(str(uuid.uuid4()))

    def test_postwrite_guard_failure_invalidates_current_owner(self):
        changed = [False]
        def validate(expected):
            if changed[0]:
                raise ChallengeError("synthetic persisted scope unavailable")
        owner = self.owner(validate=validate)
        replace = self.storage.replace
        def write(data, expecting):
            replace(data, expecting=expecting)
            changed[0] = True
        with patch.object(self.storage, "replace", side_effect=write):
            with self.assertRaises(ChallengeError):
                self.admit(owner)
        changed[0] = False
        with self.assertRaises(ChallengeError):
            owner.restore_recovery_required()
        restarted = self.owner()
        restarted.require_recovery_handle(restarted.restore_recovery_required())

    def test_final_publication_guard_delay_rechecks_original_deadline(self):
        written, checks = [False], [0]
        def validate(expected):
            if written[0]:
                checks[0] += 1
                if checks[0] == 2:
                    self.f.time += 120
        owner = self.owner(validate=validate)
        replace = self.storage.replace
        def write(data, expecting):
            replace(data, expecting=expecting)
            written[0] = True
        with patch.object(self.storage, "replace", side_effect=write):
            with self.assertRaises(ChallengeError):
                self.admit(owner)
        self.assertIsNotNone(self.storage.load())
        with self.assertRaises(ChallengeError):
            owner.snapshot(str(uuid.uuid4()))
        with self.assertRaises(ChallengeError):
            owner.restore_recovery_required()

    def test_policy_registration_delay_rechecks_original_deadline(self):
        owner = self.owner()
        register = self.lease.register
        def delayed(continuity):
            register(continuity)
            self.f.time += 120
        with patch.object(self.lease, "register", side_effect=delayed):
            with self.assertRaises(ChallengeError):
                self.admit(owner)
        self.assertIsNotNone(self.storage.load())
        with self.assertRaises(ChallengeError):
            owner.snapshot(str(uuid.uuid4()))
        with self.assertRaises(ChallengeError):
            owner.restore_recovery_required()
