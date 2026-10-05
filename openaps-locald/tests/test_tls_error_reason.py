"""Diagnostic tokens must remain static even with attacker-controlled errors."""
import unittest

from openaps_locald.authorization_tls import TLSError
from openaps_locald.http_api import _tls_error_reason
from openaps_locald.write_challenge import ChallengeError


class TLSErrorReasonTests(unittest.TestCase):
    def test_registry_failures_have_bounded_reasons(self):
        cases = {
            "registry peer not admitted": "registry_peer_not_admitted",
            "registry invalidated": "registry_invalidated",
            "registry peer key changed": "registry_peer_key_changed",
            "registry peer context changed": "registry_peer_context_changed",
            "recovery witness unavailable": "recovery_witness_unavailable",
        }
        for message, expected in cases.items():
            self.assertEqual(_tls_error_reason(ChallengeError(message)), expected)

    def test_unknown_or_wrong_exception_type_never_echoes_text(self):
        for error in (ChallengeError("synthetic secret"),
                      ChallengeError("registry peer not admitted: synthetic secret"),
                      ValueError("registry peer not admitted"),
                      TLSError("synthetic secret")):
            self.assertEqual(_tls_error_reason(error), "unclassified")

    def test_existing_tls_reason_is_preserved(self):
        self.assertEqual(_tls_error_reason(TLSError("invalid stream hello")),
                         "invalid_stream_hello")


if __name__ == "__main__":
    unittest.main()
