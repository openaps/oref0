from __future__ import print_function

import fcntl
import hashlib
import os
import subprocess
import tempfile
import threading
import time


SIGNING_ALGORITHM = "ecdsa-p256-sha256"
PRIVATE_KEY_BASENAME = "device-authorization-private.pem"
PUBLIC_KEY_BASENAME = "device-authorization-public.der"
MAX_PUBLIC_KEY_DER_BYTES = 512
MAX_SIGNATURE_DER_BYTES = 80
P256_SPKI_PREFIX = bytes.fromhex(
    "3059301306072a8648ce3d020106082a8648ce3d03010703420004"
)
DEFAULT_OPENSSL_PATH = "/usr/bin/openssl"
ALLOWED_OPENSSL_PATHS = set([
    "/usr/bin/openssl",
    "/usr/local/bin/openssl",
])
_OPENSSL_CONCURRENCY = threading.BoundedSemaphore(1)


class IdentityError(Exception):
    pass


def _openssl_path(value=None):
    path = value or DEFAULT_OPENSSL_PATH
    if path not in ALLOWED_OPENSSL_PATHS:
        raise IdentityError("unsupported OpenSSL path")
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise IdentityError("OpenSSL executable unavailable")
    return path


def _run_openssl(args, input_bytes=None, timeout=5, lock_path=None):
    if not args or args[0] not in ALLOWED_OPENSSL_PATHS:
        raise IdentityError("invalid OpenSSL command")
    if not _OPENSSL_CONCURRENCY.acquire(timeout=1):
        raise IdentityError("OpenSSL verifier is busy")
    lock_path = lock_path or os.path.join(
        tempfile.gettempdir(),
        "openaps-device-authorization-openssl-%s.lock" % os.getuid(),
    )
    lock_descriptor = None
    try:
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lock_descriptor = os.open(lock_path, flags, 0o600)
        os.fchmod(lock_descriptor, 0o600)
        lock_deadline = time.monotonic() + 1.0
        while True:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (IOError, OSError):
                if time.monotonic() >= lock_deadline:
                    raise IdentityError("OpenSSL verifier is busy")
                time.sleep(0.02)
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input_bytes is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        try:
            stdout, _stderr = process.communicate(input=input_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise IdentityError("OpenSSL operation timed out")
        if process.returncode != 0:
            raise IdentityError("OpenSSL operation failed")
        return stdout
    finally:
        if lock_descriptor is not None:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            finally:
                os.close(lock_descriptor)
        _OPENSSL_CONCURRENCY.release()


def _read_der_length(data, offset):
    if offset >= len(data):
        raise IdentityError("truncated DER length")
    first = data[offset]
    if not isinstance(first, int):
        first = ord(first)
    offset += 1
    if first < 0x80:
        return first, offset
    count = first & 0x7f
    if count == 0 or count > 2 or offset + count > len(data):
        raise IdentityError("invalid DER length")
    if count > 1:
        leading = data[offset]
        if not isinstance(leading, int):
            leading = ord(leading)
        if leading == 0:
            raise IdentityError("non-canonical DER length")
    value = 0
    for index in range(count):
        byte = data[offset + index]
        if not isinstance(byte, int):
            byte = ord(byte)
        value = (value << 8) | byte
    if value < 0x80:
        raise IdentityError("non-canonical DER length")
    return value, offset + count


def _read_der_integer(data, offset):
    if offset >= len(data):
        raise IdentityError("truncated DER integer")
    tag = data[offset]
    if not isinstance(tag, int):
        tag = ord(tag)
    if tag != 0x02:
        raise IdentityError("invalid DER integer tag")
    length, start = _read_der_length(data, offset + 1)
    end = start + length
    if length < 1 or end > len(data):
        raise IdentityError("invalid DER integer length")
    first = data[start]
    if not isinstance(first, int):
        first = ord(first)
    if first & 0x80:
        raise IdentityError("negative DER integer")
    if length > 1 and first == 0:
        second = data[start + 1]
        if not isinstance(second, int):
            second = ord(second)
        if not (second & 0x80):
            raise IdentityError("padded DER integer")
    return end


def validate_signature_der(signature_der):
    if not isinstance(signature_der, bytes):
        raise IdentityError("signature must be bytes")
    if len(signature_der) < 8 or len(signature_der) > MAX_SIGNATURE_DER_BYTES:
        raise IdentityError("signature length is invalid")
    first = signature_der[0]
    if not isinstance(first, int):
        first = ord(first)
    if first != 0x30:
        raise IdentityError("signature is not a DER sequence")
    sequence_length, offset = _read_der_length(signature_der, 1)
    if offset + sequence_length != len(signature_der):
        raise IdentityError("signature DER has trailing or missing bytes")
    offset = _read_der_integer(signature_der, offset)
    offset = _read_der_integer(signature_der, offset)
    if offset != len(signature_der):
        raise IdentityError("signature DER has extra fields")
    return signature_der


def credential_id_for_public_key(public_key_der):
    if not isinstance(public_key_der, bytes):
        raise IdentityError("public key must be bytes")
    digest = hashlib.sha256(
        SIGNING_ALGORITHM.encode("ascii") + b"\x00" + public_key_der
    ).hexdigest()
    return digest.lower()


def _atomic_write(path, payload, mode):
    directory = os.path.dirname(path)
    fd, temporary_path = tempfile.mkstemp(prefix=".openaps-auth-", dir=directory)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temporary_path, path)
        os.chmod(path, mode)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def validate_public_key_der(public_key_der, openssl_path=None, lock_path=None):
    if not isinstance(public_key_der, bytes):
        raise IdentityError("public key must be bytes")
    if len(public_key_der) != 91 or not public_key_der.startswith(P256_SPKI_PREFIX):
        raise IdentityError("public key length is invalid")
    executable = _openssl_path(openssl_path)
    canonical = _run_openssl([
        executable,
        "pkey",
        "-pubin",
        "-inform",
        "DER",
        "-outform",
        "DER",
    ], input_bytes=public_key_der, lock_path=lock_path)
    if canonical != public_key_der:
        raise IdentityError("public key DER is not canonical")
    return public_key_der


class DeviceIdentity(object):
    def __init__(self, directory, openssl_path=None):
        self.directory = os.path.abspath(directory)
        self.openssl_path = _openssl_path(openssl_path)
        self.private_key_path = os.path.join(self.directory, PRIVATE_KEY_BASENAME)
        self.public_key_path = os.path.join(self.directory, PUBLIC_KEY_BASENAME)
        self.peer_directory = os.path.join(self.directory, "authorized-peer-keys")
        self.openssl_lock_path = os.path.join(self.directory, ".openssl.lock")
        self._ensure_identity()
        self.public_key_der = self._export_public_key_der()
        validate_public_key_der(self.public_key_der, self.openssl_path, self.openssl_lock_path)
        self.credential_id = credential_id_for_public_key(self.public_key_der)
        if not os.path.exists(self.public_key_path) or self._read(self.public_key_path) != self.public_key_der:
            _atomic_write(self.public_key_path, self.public_key_der, 0o600)

    @staticmethod
    def _read(path):
        with open(path, "rb") as handle:
            return handle.read()

    def _ensure_identity(self):
        if not os.path.exists(self.directory):
            os.makedirs(self.directory, 0o700)
        os.chmod(self.directory, 0o700)
        lock_path = os.path.join(self.directory, ".identity.lock")
        with open(lock_path, "a") as lock:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not os.path.exists(self.private_key_path):
                fd, temporary_path = tempfile.mkstemp(prefix=".device-key-", dir=self.directory)
                os.close(fd)
                try:
                    os.chmod(temporary_path, 0o600)
                    _run_openssl([
                        self.openssl_path,
                        "ecparam",
                        "-name",
                        "prime256v1",
                        "-genkey",
                        "-noout",
                        "-out",
                        temporary_path,
                    ], lock_path=self.openssl_lock_path)
                    os.chmod(temporary_path, 0o600)
                    _run_openssl([
                        self.openssl_path,
                        "ec",
                        "-in",
                        temporary_path,
                        "-noout",
                    ], lock_path=self.openssl_lock_path)
                    os.rename(temporary_path, self.private_key_path)
                    directory_fd = os.open(self.directory, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                finally:
                    if os.path.exists(temporary_path):
                        os.unlink(temporary_path)
            os.chmod(self.private_key_path, 0o600)
            _run_openssl([
                self.openssl_path,
                "ec",
                "-in",
                self.private_key_path,
                "-noout",
            ], lock_path=self.openssl_lock_path)

    def _export_public_key_der(self):
        return _run_openssl([
            self.openssl_path,
            "ec",
            "-in",
            self.private_key_path,
            "-pubout",
            "-outform",
            "DER",
        ], lock_path=self.openssl_lock_path)

    def sign(self, message):
        if not isinstance(message, bytes):
            raise IdentityError("message must be bytes")
        signature = _run_openssl([
            self.openssl_path,
            "dgst",
            "-sha256",
            "-sign",
            self.private_key_path,
        ], input_bytes=message, lock_path=self.openssl_lock_path)
        return validate_signature_der(signature)

    def cache_peer_public_key(self, credential_id, public_key_der):
        validate_public_key_der(public_key_der, self.openssl_path, self.openssl_lock_path)
        if credential_id_for_public_key(public_key_der) != credential_id:
            raise IdentityError("peer credential does not match public key")
        if not os.path.exists(self.peer_directory):
            os.makedirs(self.peer_directory, 0o700)
        os.chmod(self.peer_directory, 0o700)
        der_path = os.path.join(self.peer_directory, credential_id + ".der")
        pem_path = os.path.join(self.peer_directory, credential_id + ".pem")
        pem = _run_openssl([
            self.openssl_path,
            "pkey",
            "-pubin",
            "-inform",
            "DER",
            "-outform",
            "PEM",
        ], input_bytes=public_key_der, lock_path=self.openssl_lock_path)
        if not os.path.exists(der_path) or self._read(der_path) != public_key_der:
            _atomic_write(der_path, public_key_der, 0o600)
        if not os.path.exists(pem_path) or self._read(pem_path) != pem:
            _atomic_write(pem_path, pem, 0o600)
        return pem_path

    def load_cached_peer_public_key(self, credential_id):
        if not isinstance(credential_id, str) or len(credential_id) != 64:
            raise IdentityError("peer credential is invalid")
        der_path = os.path.join(self.peer_directory, credential_id + ".der")
        public_key_der = self._read(der_path)
        validate_public_key_der(public_key_der, self.openssl_path, self.openssl_lock_path)
        if credential_id_for_public_key(public_key_der) != credential_id:
            raise IdentityError("cached peer credential mismatch")
        return public_key_der

    def verify(self, message, signature_der, credential_id, public_key_der):
        if not isinstance(message, bytes):
            raise IdentityError("message must be bytes")
        validate_signature_der(signature_der)
        pem_path = self.cache_peer_public_key(credential_id, public_key_der)
        # OpenSSL 1.1.0 requires the signature as a file. Use a bounded 0600
        # temporary file instead of shell expansion.
        fd, signature_path = tempfile.mkstemp(prefix=".signature-", dir=self.peer_directory)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, signature_der)
            os.fsync(fd)
            os.close(fd)
            fd = None
            try:
                _run_openssl([
                    self.openssl_path,
                    "dgst",
                    "-sha256",
                    "-verify",
                    pem_path,
                    "-signature",
                    signature_path,
                ], input_bytes=message, lock_path=self.openssl_lock_path)
                return True
            except IdentityError:
                return False
        finally:
            if fd is not None:
                os.close(fd)
            if os.path.exists(signature_path):
                os.unlink(signature_path)
