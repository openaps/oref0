"""Live-owner continuity bookkeeping, not provenance or persisted trust.

Construct after confirmed admission/recovery commit only. Never reconstruct a
live clock owner from persisted timestamps. Caller serializes access and binds
this value to the exact admitted peer and current configuration.
"""
import math
from .authorization_tls import boottime


class ContinuityError(Exception):
    pass


class BoundContinuity:
    """Exact admission scope; connection IDs may differ across BLE/HTTP routes.

    Caller serializes checks with admission changes. This wrapper does not
    establish provenance or confer authority on a caller-created state.
    """
    def __init__(self, state, binding):
        if not isinstance(state, Continuity):
            raise ContinuityError("live continuity required")
        self._scope = self._scope_for(binding)
        self._state = state
        self._valid = True

    @staticmethod
    def _scope_for(binding):
        if (not isinstance(binding, tuple) or len(binding) != 5 or
                not all(isinstance(value, str) and 0 < len(value) <= 128 for value in binding)):
            raise ContinuityError("continuity scope")
        return binding[:3] + binding[4:]

    def require_current(self, binding):
        if not self._valid or self._scope_for(binding) != self._scope:
            raise ContinuityError("continuity scope changed")
        self._state.require_current()
        if not self._valid:
            raise ContinuityError("continuity invalidated")

    def invalidate(self):
        """Terminal admission removal, including already retained snapshots."""
        self._valid = False

    def authenticated_direct_contact(self, binding):
        """Normal TLS only; restricted recovery must never renew contact."""
        self.require_current(binding)
        self._state.authenticated_direct_contact()
        self.require_current(binding)

    def witness_response(self, request, identity, binding):
        """Restricted response, never contact renewal. Caller reserves budgets."""
        from . import recovery_challenge as codec
        self.require_current(binding)
        fields = codec.validate_request(request)
        authority, local, peer, generation = self._scope
        if (fields["authority_context_id"] != authority or
                fields["requester_credential_id"] != peer or
                fields["witness_credential_id"] != local or identity.credential_id != local):
            raise ContinuityError("recovery requester scope")
        age = self._state.recent_contact_age_for_recovery()
        response = codec.signed_response(fields, identity, authority, "rig", age)
        self.require_current(binding)
        self._state.recent_contact_age_for_recovery()
        return response


class Continuity:
    MAX_GAP = 86400.0

    def __init__(self, clock=boottime, recovered_age=None):
        now = clock()
        age = 0.0 if recovered_age is None else recovered_age
        if (not math.isfinite(now) or now < 0 or not math.isfinite(age) or
                not 0 <= age < self.MAX_GAP):
            raise ContinuityError("continuity confirmation required")
        self._clock = clock
        self._anchor = self._last = now
        self._inherited_age = age
        self._independent = recovered_age is None
        self._invalid = False

    def _current(self):
        now = self._clock()
        if (self._invalid or not math.isfinite(now) or now < self._last or
                self._inherited_age + (now - self._anchor) >= self.MAX_GAP):
            self._invalid = True
            raise ContinuityError("continuity confirmation required")
        self._last = now
        return now

    def require_current(self):
        self._current()

    def authenticated_direct_contact(self):
        self._anchor = self._current()
        self._inherited_age = 0.0
        self._independent = True

    def recent_contact_age_for_recovery(self):
        now = self._current()
        if not self._independent:
            raise ContinuityError("independent contact required")
        return now - self._anchor
