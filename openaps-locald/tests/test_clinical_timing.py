import unittest
from unittest.mock import patch

from openaps_locald.clinical_timing import timed_clinical_call


class ClinicalTimingTests(unittest.TestCase):
    def test_reports_duration_without_operation_content(self):
        messages = []
        secret_result = object()
        with patch("openaps_locald.clinical_timing.time.monotonic", side_effect=[10, 10.125]):
            result = timed_clinical_call(messages.append, "event_insert", lambda: secret_result)
        self.assertIs(result, secret_result)
        self.assertEqual(messages, ["clinical timing stage=event_insert elapsed_ms=125"])

    def test_diagnostic_failure_preserves_result_and_original_exception(self):
        def failed_logger(message):
            raise RuntimeError("diagnostic unavailable")
        self.assertEqual(timed_clinical_call(failed_logger, "event_insert", lambda: 7), 7)
        primary = ValueError("synthetic operation failed")
        def failed_operation():
            raise primary
        with self.assertRaises(ValueError) as caught:
            timed_clinical_call(failed_logger, "event_insert", failed_operation)
        self.assertIs(caught.exception, primary)
