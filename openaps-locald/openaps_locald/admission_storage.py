"""Private bounded whole-file storage, NOT an admission or restore validator.

The runtime supplies an existing private directory, distinct from shadow
trust. No installed runtime uses this adapter yet. Errors after rename may
mean the new bytes are present; never infer rollback or activate on error.
"""
import contextlib
import fcntl
import os
import stat
import threading
import uuid

MAX_BYTES = 128 * 1024
RECORD = "provenance-admission-v1.json"
LOCK = ".provenance-admission-v1.lock"
_UNCONDITIONAL = object()


class StorageError(Exception):
    pass


def _private(fd, directory=False):
    info = os.fstat(fd)
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (not correct_type or info.st_uid != os.geteuid() or info.st_mode & 0o077 or
            (not directory and info.st_nlink != 1)):
        raise StorageError("storage must be private and owned by this process user")
    return info


class AdmissionStorage:
    def __init__(self, directory):
        if not os.path.isabs(directory):
            raise StorageError("explicit absolute storage directory required")
        self._directory = directory
        self._operation = threading.Lock()

    @contextlib.contextmanager
    def _transaction(self):
        if not self._operation.acquire(False):
            raise StorageError("storage busy")
        root = lock = None
        try:
            root = os.open(self._directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            _private(root, directory=True)
            lock = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root)
            _private(lock)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield root
        finally:
            try:
                if lock is not None:
                    os.close(lock)  # Releases the cooperative cross-process lock.
            finally:
                try:
                    if root is not None:
                        os.close(root)
                finally:
                    self._operation.release()

    def _load(self, root):
        try:
            fd = os.open(RECORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        except FileNotFoundError:
            return None
        try:
            info = _private(fd)
            if not 0 < info.st_size <= MAX_BYTES:
                raise StorageError("invalid stored size")
            data = b""
            while len(data) <= MAX_BYTES:
                chunk = os.read(fd, MAX_BYTES + 1 - len(data))
                if not chunk:
                    break
                data += chunk
            if len(data) != info.st_size or not 0 < len(data) <= MAX_BYTES:
                raise StorageError("storage changed or exceeded bounds")
            return data
        finally:
            os.close(fd)

    def load(self):
        with self._transaction() as root:
            return self._load(root)

    def replace(self, data, expecting=_UNCONDITIONAL):
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
            raise StorageError("invalid replacement size")
        if (expecting is not _UNCONDITIONAL and expecting is not None and
                (not isinstance(expecting, bytes) or not 0 < len(expecting) <= MAX_BYTES)):
            raise StorageError("invalid expected snapshot")
        with self._transaction() as root:
            # Validate an existing target before replacing it; no symlinks,
            # non-private files or corrupt oversized recovery copies overwritten.
            current = self._load(root)
            if expecting is not _UNCONDITIONAL:
                if current != expecting:
                    raise StorageError("storage conflict")
                # Check the snapshot under the cooperative lock even when the
                # caller believes this is an idempotent repeat.
                if current == data:
                    return
            temporary = ".admission-candidate-" + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
            created = True
            try:
                remaining = memoryview(data)
                while remaining:
                    count = os.write(fd, remaining)
                    if count <= 0:
                        raise StorageError("no write progress")
                    remaining = remaining[count:]
                os.fsync(fd)
                os.close(fd)
                fd = None
                os.replace(temporary, RECORD, src_dir_fd=root, dst_dir_fd=root)
                created = False
                os.fsync(root)
                if self._load(root) != data:
                    raise StorageError("replacement readback mismatch")
            finally:
                try:
                    if fd is not None:
                        os.close(fd)
                finally:
                    if created:
                        os.unlink(temporary, dir_fd=root)
