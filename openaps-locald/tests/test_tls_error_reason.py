import unittest

from openaps_locald.authorization_tls import TLSError
from openaps_locald.http_api import _tls_error_reason
from openaps_locald.write_challenge import ChallengeError


class TLSErrorReasonTests(unittest.TestCase):
    def test_known_admission_failure_has_static_reason(self):
        self.assertEqual(
            _tls_error_reason(ChallengeError("registry peer not admitted")),
            "registry_peer_not_admitted",
        )
        self.assertEqual(
            _tls_error_reason(ChallengeError("admission unavailable")),
            "admission_unavailable",
        )

    def test_unknown_exception_text_is_not_logged(self):
        self.assertEqual(_tls_error_reason(ChallengeError("secret token value")), "unclassified")
        self.assertEqual(_tls_error_reason(TLSError("secret token value")), "unclassified")
        self.assertEqual(_tls_error_reason(ValueError("secret token value")), "unclassified")


if __name__ == "__main__":
    unittest.main()
