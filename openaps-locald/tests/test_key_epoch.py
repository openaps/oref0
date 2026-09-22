import json
import tempfile
import unittest
from unittest.mock import patch

from openaps_locald.admission_storage import AdmissionStorage
from openaps_locald.key_epoch import KeyEpochError, KeyEpochStore


class KeyEpochTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="synthetic-key-epoch-")
        self.addCleanup(directory.cleanup)
        self.storage = AdmissionStorage(directory.name)
        self.store = KeyEpochStore(self.storage)
        self.key = "a" * 64

    def test_restart_preserves_epoch_without_rewrite(self):
        epoch = self.store.bootstrap_fresh_enrollment(self.key)
        restarted = KeyEpochStore(self.storage)
        with patch.object(self.storage, "replace", side_effect=AssertionError("rewrite")):
            self.assertEqual(restarted.load_existing(self.key), epoch)
            self.assertEqual(restarted.bootstrap_fresh_enrollment(self.key), epoch)

    def test_missing_restore_does_not_create(self):
        with self.assertRaises(KeyEpochError):
            self.store.load_existing(self.key)
        self.assertIsNone(self.storage.load())

    def test_wrong_key_never_repairs(self):
        self.store.bootstrap_fresh_enrollment(self.key)
        original = self.storage.load()
        for method in (self.store.load_existing, self.store.bootstrap_fresh_enrollment):
            with self.assertRaises(KeyEpochError):
                method("b" * 64)
        self.assertEqual(self.storage.load(), original)

    def test_corrupt_schema_never_repairs(self):
        good = {"schema": "openaps.key-epoch.v1", "key_credential_id": self.key,
                "epoch": "11111111-1111-4111-8111-111111111111"}
        bad = [b"{", b"x" * 257, b"[]", json.dumps(dict(good, extra="x")).encode(),
               json.dumps(dict(good, schema="unknown")).encode(),
               json.dumps(dict(good, epoch="not-uuid")).encode(),
               json.dumps(dict(good, epoch="00000000-0000-0000-0000-000000000000")).encode(),
               (json.dumps(good)[:-1] + ',"epoch":"11111111-1111-4111-8111-111111111111"}').encode()]
        for data in bad:
            self.storage.replace(data)
            for method in (self.store.load_existing, self.store.bootstrap_fresh_enrollment):
                with self.assertRaises(KeyEpochError):
                    method(self.key)
            self.assertEqual(self.storage.load(), data)

    def test_write_failure_poisoned_even_if_rename_happened(self):
        replace = self.storage.replace
        def ambiguous(data, expecting):
            replace(data, expecting=expecting)
            raise OSError("synthetic post-rename failure")
        with patch.object(self.storage, "replace", side_effect=ambiguous):
            with self.assertRaises(KeyEpochError):
                self.store.bootstrap_fresh_enrollment(self.key)
        with self.assertRaises(KeyEpochError):
            self.store.load_existing(self.key)
        self.assertIsNotNone(KeyEpochStore(self.storage).load_existing(self.key))

    def test_readback_mismatch_poisoned_and_no_false_success(self):
        with patch.object(self.storage, "load", side_effect=[None, b"wrong"]):
            with self.assertRaises(KeyEpochError):
                self.store.bootstrap_fresh_enrollment(self.key)
        with self.assertRaises(KeyEpochError):
            self.store.bootstrap_fresh_enrollment(self.key)

    def test_prewrite_failure_does_not_create(self):
        with patch.object(self.storage, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(KeyEpochError):
                self.store.bootstrap_fresh_enrollment(self.key)
        self.assertIsNone(self.storage.load())

    def test_invalid_key_rejected_before_storage(self):
        with patch.object(self.storage, "load", side_effect=AssertionError("storage read")):
            for key in (None, "A" * 64, "a" * 63, self.key + "\n"):
                with self.assertRaises(KeyEpochError):
                    self.store.bootstrap_fresh_enrollment(key)
