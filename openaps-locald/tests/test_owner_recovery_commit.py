"""Joined synthetic proof admission/restart/TLS/recovery commit; no live rig."""
import unittest
import uuid
from unittest.mock import patch

from openaps_locald.authorization_tls import issue_local_certificate
from openaps_locald.continuity import ContinuityError
from openaps_locald.recovery_tls import RecoveryHello, RecoveryReservation
from openaps_locald.recovery_tls_client import RecoveryTLSClient
from openaps_locald.write_challenge import ChallengeError
from tests import test_admission_restore, test_recovery_tls_client
from openaps_locald import admission_owner as owner_module


class OwnerRecoveryCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_recovery_tls_client.RecoveryTLSClientTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        test_recovery_tls_client.RecoveryTLSClientTests.tearDownClass()

    def setUp(self):
        self.f = test_admission_restore.AdmissionRestoreTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.admit(self.f.owner())
        self.owner = self.f.owner()
        self.handle = self.owner.restore_recovery_required()

    def transport(self, attempt):
        h = test_recovery_tls_client.RecoveryTLSClientTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.f.rig, h.f.phone = self.f.f.rig, self.f.f.phone
        h.f.authority = self.f.context.authority
        h.f.rig_hello = RecoveryHello(2, issue_local_certificate(h.f.rig).der)
        h.f.phone_hello = RecoveryHello(1, issue_local_certificate(h.f.phone).der)
        reservation = RecoveryReservation(h.f.pool, h.f.pool.acquire(None), self.f.f.time,
                                          clock=lambda: self.f.f.time)
        h.f.reservations.append(reservation)
        engine = RecoveryTLSClient(h.f.rig, h.f.rig_hello, h.f.phone_hello.encode(),
                                  attempt.admission, reservation, attempt.exchange)
        self.addCleanup(engine.close)
        h.complete(engine)
        for sock in h.sockets:
            sock.close()
        return engine, engine.transport_terminated()

    def test_joined_restart_tls_commit_new_session_and_uncertain_witness(self):
        attempt = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        engine, completion = self.transport(attempt)
        revision = self.owner.commit_recovery(attempt, engine, completion)
        snapshot = self.owner.snapshot(str(uuid.uuid4()))
        self.assertEqual(snapshot["trust_generation"], str(revision))
        with self.assertRaises(ContinuityError):
            snapshot["continuity"]._state.recent_contact_age_for_recovery()
        with self.assertRaises(ChallengeError):
            self.owner.snapshot(attempt.connection)
        with self.assertRaises(Exception):
            self.owner.commit_recovery(attempt, engine, completion)
        self.owner.snapshot(str(uuid.uuid4()))  # Replay cannot revoke successful admission.
        restarted = self.f.owner()
        restarted.require_recovery_handle(restarted.restore_recovery_required())
        with self.assertRaises(ChallengeError):
            restarted.snapshot(str(uuid.uuid4()))

    def test_foreign_evidence_and_stale_cancellation_do_not_cancel_new_attempt(self):
        old = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        self.owner.cancel_recovery(old)
        current = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        self.owner.cancel_recovery(old)
        engine, completion = self.transport(current)
        with self.assertRaises(ChallengeError):
            self.owner.commit_recovery(old, engine, completion)
        current.admission()
        self.owner.commit_recovery(current, engine, completion)

    def test_ambiguous_write_poison_current_owner_but_restart_requires_recovery(self):
        attempt = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        engine, completion = self.transport(attempt)
        replace = self.f.storage.replace
        def ambiguous(data, expecting):
            replace(data, expecting=expecting)
            raise OSError("synthetic post-write failure")
        with patch.object(self.f.storage, "replace", side_effect=ambiguous):
            with self.assertRaises(OSError):
                self.owner.commit_recovery(attempt, engine, completion)
        with self.assertRaises(ChallengeError):
            self.owner.restore_recovery_required()
        restarted = self.f.owner()
        restarted.require_recovery_handle(restarted.restore_recovery_required())

    def test_poststorage_deadline_delay_denies_publication(self):
        attempt = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        engine, completion = self.transport(attempt)
        replace = self.f.storage.replace
        def delayed(data, expecting):
            replace(data, expecting=expecting)
            self.f.f.time += 20
        with patch.object(self.f.storage, "replace", side_effect=delayed):
            with self.assertRaises(Exception):
                self.owner.commit_recovery(attempt, engine, completion)
        with self.assertRaises(ChallengeError):
            self.owner.snapshot(str(uuid.uuid4()))

    def test_delayed_policy_registration_denies_activation(self):
        attempt = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        engine, completion = self.transport(attempt)
        register = self.f.lease.register
        def delayed(continuity):
            register(continuity)
            self.f.f.time += 20
        with patch.object(self.f.lease, "register", side_effect=delayed):
            with self.assertRaises(Exception):
                self.owner.commit_recovery(attempt, engine, completion)
        with self.assertRaises(ChallengeError):
            self.owner.snapshot(str(uuid.uuid4()))
        with self.assertRaises(ChallengeError):
            self.owner.restore_recovery_required()

    def test_constructor_delay_is_not_discarded_from_recovered_age(self):
        attempt = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        engine, completion = self.transport(attempt)
        original = owner_module.Continuity
        def delayed(**kwargs):
            self.f.f.time += 5
            return original(**kwargs)
        with patch.object(owner_module, "Continuity", side_effect=delayed):
            self.owner.commit_recovery(attempt, engine, completion)
        state = self.owner.snapshot(str(uuid.uuid4()))["continuity"]._state
        self.assertGreaterEqual(state._inherited_age + self.f.f.time - state._anchor, 105)
        self.f.f.time += 2
        self.assertGreaterEqual(state._inherited_age + state._current() - state._anchor, 107)

    def test_final_state_clock_cancellation_cannot_publish(self):
        attempt = self.owner.begin_recovery(self.handle, str(uuid.uuid4()))
        engine, completion = self.transport(attempt)
        original = owner_module.Continuity
        def cancelling(**kwargs):
            state = original(**kwargs)
            current = state.require_current
            def cancel_then_check():
                self.owner.cancel_recovery(attempt)
                return current()
            state.require_current = cancel_then_check
            return state
        with patch.object(owner_module, "Continuity", side_effect=cancelling):
            with self.assertRaises(Exception):
                self.owner.commit_recovery(attempt, engine, completion)
        with self.assertRaises(ChallengeError):
            self.owner.snapshot(str(uuid.uuid4()))
