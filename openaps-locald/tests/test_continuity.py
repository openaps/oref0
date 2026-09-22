import unittest
from openaps_locald.continuity import Continuity, BoundContinuity
from openaps_locald.continuity import ContinuityError as ChallengeError


class ContinuityTests(unittest.TestCase):
    def test_scope_binding_excludes_only_connection_identity(self):
        binding = ("ns_" + "a" * 64, "b" * 64, "c" * 64, "connection", "trust")
        owner = BoundContinuity(Continuity(clock=lambda: 0), binding)
        for index in range(5):
            candidate = list(binding)
            candidate[index] = "different"
            if index == 3:
                owner.require_current(tuple(candidate))
            else:
                with self.assertRaises(ChallengeError):
                    owner.require_current(tuple(candidate))
        owner.require_current(binding)
        for bad in (None, (), binding[:-1], list(binding)):
            with self.assertRaises(ChallengeError):
                owner.require_current(bad)

    def test_recovered_age_preserves_expiry_and_cannot_witness(self):
        now = [0.5]
        state = Continuity(clock=lambda: now[0], recovered_age=86390)
        now[0] = 1
        with self.assertRaises(ChallengeError):
            state.recent_contact_age_for_recovery()
        now[0] = 10.499
        state.require_current()
        now[0] = 10.5
        with self.assertRaises(ChallengeError):
            state.authenticated_direct_contact()
        now[0] = 2
        with self.assertRaises(ChallengeError):
            state.require_current()

    def test_only_independent_contact_enables_witness_and_queries_do_not_renew(self):
        now = [1]
        state = Continuity(clock=lambda: now[0], recovered_age=80000)
        now[0] = 4
        state.authenticated_direct_contact()
        now[0] = 5
        self.assertEqual(state.recent_contact_age_for_recovery(), 1)
        now[0] = 86403
        self.assertEqual(state.recent_contact_age_for_recovery(), 86399)
        now[0] = 86404
        with self.assertRaises(ChallengeError):
            state.recent_contact_age_for_recovery()

    def test_invalid_age_and_sticky_clock_failure(self):
        for age in (-1, float("nan"), float("inf"), 86400):
            with self.assertRaises(ChallengeError):
                Continuity(clock=lambda: 0, recovered_age=age)
        for bad in (-1, float("nan"), float("inf"), 9):
            now = [10]
            state = Continuity(clock=lambda: now[0])
            now[0] = bad
            with self.assertRaises(ChallengeError):
                state.require_current()
            now[0] = 11
            with self.assertRaises(ChallengeError):
                state.authenticated_direct_contact()
