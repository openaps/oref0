import fcntl
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from openaps_locald import admission_storage as module


class AdmissionStorageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="openaps-admission-storage-")
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        self.store = module.AdmissionStorage(self.directory)
        self.path = os.path.join(self.directory, module.RECORD)

    def test_absent_replace_and_boundary_roundtrip(self):
        self.assertIsNone(self.store.load())
        for data in (b"synthetic-first", b"synthetic-second", b"x" * module.MAX_BYTES):
            self.store.replace(data)
            self.assertEqual(self.store.load(), data)
            self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertFalse(any(name.startswith(".admission-candidate-") for name in os.listdir(self.directory)))

    def test_conditional_replace_rejects_stale_snapshot_across_owners(self):
        other = module.AdmissionStorage(self.directory)
        self.store.replace(b"first", expecting=None)
        snapshot = self.store.load()
        other.replace(b"second", expecting=snapshot)
        for expected in (None, snapshot):
            with self.assertRaises(module.StorageError):
                self.store.replace(b"third", expecting=expected)
        # Even same-data requests cannot waive the expected-snapshot check.
        with self.assertRaises(module.StorageError):
            self.store.replace(b"second", expecting=snapshot)
        self.assertEqual(self.store.load(), b"second")
        with patch.object(module.os, "replace", side_effect=AssertionError("unnecessary write")):
            self.store.replace(b"second", expecting=b"second")
        self.assertFalse(any(name.startswith(".admission-candidate-") for name in os.listdir(self.directory)))

    def test_invalid_expected_snapshot_rejected_before_filesystem(self):
        for expected in (b"", "not-bytes", b"x" * (module.MAX_BYTES + 1)):
            with self.assertRaises(module.StorageError):
                self.store.replace(b"new", expecting=expected)
        self.assertEqual(os.listdir(self.directory), [])

    def test_bad_replacement_rejected_before_filesystem_and_corrupt_store_preserved(self):
        for data in (b"", b"x" * (module.MAX_BYTES + 1), "not-bytes"):
            with self.assertRaises(module.StorageError):
                self.store.replace(data)
        self.assertEqual(os.listdir(self.directory), [])
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with self.assertRaises(module.StorageError):
            self.store.load()
        with self.assertRaises(module.StorageError):
            self.store.replace(b"new")
        self.assertEqual(os.stat(self.path).st_size, 0)

    def test_symlink_and_nonprivate_targets_rejected(self):
        other = os.path.join(self.directory, "synthetic-other")
        with open(other, "wb") as handle:
            handle.write(b"unchanged")
        os.symlink(other, self.path)
        with self.assertRaises(OSError):
            self.store.replace(b"new")
        with open(other, "rb") as handle:
            self.assertEqual(handle.read(), b"unchanged")
        os.unlink(self.path)
        os.rename(other, self.path)
        os.chmod(self.path, 0o644)
        with self.assertRaises(module.StorageError):
            self.store.load()

    def test_replace_failure_preserves_old_file_and_cleans_candidate(self):
        self.store.replace(b"old")
        with patch.object(module.os, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.store.replace(b"new")
        self.assertEqual(self.store.load(), b"old")
        self.assertFalse(any(name.startswith(".admission-candidate-") for name in os.listdir(self.directory)))

    def test_directory_sync_failure_is_ambiguous_not_reported_success(self):
        self.store.replace(b"old")
        original = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory sync failure")
            return original(fd)
        with patch.object(module.os, "fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                self.store.replace(b"new")
        self.assertEqual(self.store.load(), b"new")  # Error does not imply rollback.

    def test_contending_store_fails_without_waiting(self):
        self.assertIsNone(self.store.load())
        fd = os.open(os.path.join(self.directory, module.LOCK), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(OSError):
                module.AdmissionStorage(self.directory).replace(b"new")
        finally:
            os.close(fd)
        self.assertIsNone(self.store.load())
