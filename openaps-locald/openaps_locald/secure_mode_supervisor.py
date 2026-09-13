"""Dormant two-phase coordinator for HTTP/BLE secure-mode ownership."""
import uuid
from collections import namedtuple

from .secure_mode_contract import Binding
from .write_challenge import ChallengeError


Scope = namedtuple("Scope", "authority local_credential_id settings_epoch key_epoch "
                   "policy_generation policy_review_sha256")
Report = namedtuple("Report", "role instance scope arm abort")


class SecureModeSupervisor(object):
    """Collect two fresh owners; prepared state can never authorize enforcement."""
    def __init__(self, contract_store, enabled=False, generation_factory=uuid.uuid4):
        self.store, self.enabled = contract_store, enabled is True
        self.generation_factory = generation_factory
        self.reports, self.finished = {}, False

    def report(self, role, instance, scope, arm, abort):
        if (not self.enabled or self.finished or role not in ("http", "ble") or
                role in self.reports or not isinstance(instance, uuid.UUID) or instance.int == 0 or
                not isinstance(scope, Scope) or not callable(arm) or not callable(abort)):
            raise ChallengeError("secure-mode readiness report")
        self.reports[role] = Report(role, instance, scope, arm, abort)

    def coordinate(self):
        if not self.enabled or self.finished or set(self.reports) != {"http", "ble"}:
            raise ChallengeError("secure-mode supervisor unavailable")
        http, ble = self.reports["http"], self.reports["ble"]
        if http.scope != ble.scope or http.instance == ble.instance:
            raise ChallengeError("secure-mode readiness mismatch")
        generation = self.generation_factory()
        binding = Binding(*(tuple(http.scope) + (http.instance, ble.instance)))
        armed = []
        try:
            self.store.prepare(binding, generation)
            for report in (http, ble):
                report.arm(generation, binding)
                armed.append(report)
            # This one durable transition is the only enforcement permission.
            self.store.commit(binding, generation)
            self.finished = True
            return generation, binding
        except Exception:
            for report in reversed(armed):
                try:
                    report.abort(generation, binding)
                except Exception:
                    pass
            try:
                self.store.abort(binding, generation)
            except Exception:
                pass
            self.finished = True
            raise ChallengeError("secure-mode coordination failed") from None
