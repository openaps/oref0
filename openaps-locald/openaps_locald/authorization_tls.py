"""Bounded TLS 1.2 receiver for an admitted ordered byte stream (Python 3.5).

Not wired into clinical routes. The owner must establish enrollment provenance,
provide a fresh authorization snapshot, serialize calls, share admission across
BLE/HTTP, and call tick on a timer (also while idle). No pump or network I/O here.
"""
from __future__ import print_function

import math
import os
import ssl
import struct
import sys
import tempfile
import threading
import time

from .device_identity import (
    _run_openssl, _openssl_path, validate_public_key_der, credential_id_for_public_key,
)


MAX_CERTIFICATE = 4096
MAX_WIRE = 65536
MAX_PENDING_WIRE = 131072
HANDSHAKE_SECONDS = 20
IDLE_SECONDS = 300
ABSOLUTE_SECONDS = 1800


class TLSError(Exception):
    pass


def boottime():
    # Linux CLOCK_BOOTTIME includes suspend, unlike CLOCK_MONOTONIC. Python 3.5
    # may not export the symbolic constant, but Linux assigns it clock id 7.
    if not sys.platform.startswith("linux"):
        raise TLSError("suspend-aware clock unavailable")
    return time.clock_gettime(getattr(time, "CLOCK_BOOTTIME", 7))


class CertificateHello(object):
    def __init__(self, role, der, openssl_path=None, lock_path=None):
        if role not in (1, 2) or not isinstance(der, bytes) or not 0 < len(der) <= MAX_CERTIFICATE:
            raise TLSError("invalid hello")
        executable = _openssl_path(openssl_path)
        canonical = _run_openssl([executable, "x509", "-inform", "DER", "-outform", "DER"],
                                 input_bytes=der, lock_path=lock_path)
        if canonical != der:
            raise TLSError("noncanonical certificate")
        pem = _run_openssl([executable, "x509", "-inform", "DER", "-pubkey", "-noout"],
                          input_bytes=der, lock_path=lock_path)
        key = _run_openssl([executable, "pkey", "-pubin", "-outform", "DER"],
                          input_bytes=pem, lock_path=lock_path)
        validate_public_key_der(key, executable, lock_path)
        self.role, self.der, self.public_key_der = role, der, key
        self.credential_id = credential_id_for_public_key(key)

    @classmethod
    def decode(cls, frame, **kwargs):
        if not isinstance(frame, bytes) or not 11 < len(frame) <= 11 + MAX_CERTIFICATE:
            raise TLSError("invalid hello size")
        if frame[:8] != b"OAPSTLS\x01" or struct.unpack("!H", frame[9:11])[0] != len(frame) - 11:
            raise TLSError("invalid hello framing")
        return cls(frame[8], frame[11:], **kwargs)

    def encode(self):
        return b"OAPSTLS\x01" + bytes([self.role]) + struct.pack("!H", len(self.der)) + self.der


def issue_local_certificate(identity):
    """Issue a non-CA TLS key container without creating or rotating identity.

    Explicit configuration avoids inheriting workstation/system CA extensions.
    The certificate is public, ephemeral and never enrollment evidence.
    """
    with tempfile.TemporaryDirectory(prefix="openaps-tls-issue-") as directory:
        config = os.path.join(directory, "certificate.cnf")
        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write("[req]\ndistinguished_name=subject\nx509_extensions=leaf\n"
                         "[subject]\n[leaf]\nbasicConstraints=critical,CA:FALSE\n"
                         "keyUsage=critical,digitalSignature\n")
        der = _run_openssl([
            identity.openssl_path, "req", "-new", "-x509", "-sha256",
            "-config", config, "-key", identity.private_key_path,
            "-subj", "/CN=" + identity.credential_id, "-days", "365",
            "-set_serial", str(int.from_bytes(os.urandom(16), "big") or 1),
            "-outform", "DER",
        ], lock_path=identity.openssl_lock_path)
    hello = CertificateHello(2, der, openssl_path=identity.openssl_path,
                             lock_path=identity.openssl_lock_path)
    if hello.public_key_der != identity.public_key_der:
        raise TLSError("local certificate key mismatch")
    return hello


class LocalCertificateStore(object):
    """Process-local certificate reuse; renew daily without changing trust.

    Call from the authorization worker, not a radio callback. Existing streams
    retain their offered certificate; renewal only affects subsequent hellos.
    Nothing secret is copied and no certificate persistence is required.
    """
    def __init__(self, clock=boottime):
        self.clock = clock
        self.lock = threading.Lock()
        self.cached = None
        self.issued_at = None

    def get(self, identity):
        with self.lock:
            now = self.clock()
            if not math.isfinite(now):
                raise TLSError("invalid certificate clock")
            if (self.cached is None or self.cached.public_key_der != identity.public_key_der or
                    now < self.issued_at or now - self.issued_at >= 86400):
                issued = issue_local_certificate(identity)
                self.cached, self.issued_at = issued, now
            return self.cached


class AdmissionPool(object):
    """One pool across transports: 8 sessions, 2 per peer, 2 handshakes.

    A global six-attempt bucket refills one attempt per ten seconds. Admission
    occurs before certificate parsing/OpenSSL. Failed attempts consume a token.
    """
    def __init__(self, clock=boottime):
        self.clock = clock
        self.lock = threading.Lock()
        self.entries = {}
        self.tokens = 6.0
        self.last = None

    def acquire(self, peer):
        with self.lock:
            now = self.clock()
            if not math.isfinite(now) or (self.last is not None and now < self.last):
                raise TLSError("invalid admission clock")
            if self.last is not None:
                self.tokens = min(6.0, self.tokens + (now - self.last) / 10.0)
            self.last = now
            if (self.tokens < 1 or len(self.entries) >= 8 or
                    sum(1 for p, pending in self.entries.values() if pending) >= 2 or
                    sum(1 for p, pending in self.entries.values() if p == peer) >= 2):
                raise TLSError("admission unavailable")
            self.tokens -= 1
            token = object()
            self.entries[token] = (peer, True)
            return token

    def established(self, token):
        with self.lock:
            peer, _ = self.entries[token]
            self.entries[token] = (peer, False)

    def bind(self, token, peer):
        """Resolve an already reserved pre-hello slot without another admission."""
        with self.lock:
            if self.entries.get(token) != (None, True) or not isinstance(peer, str) or not peer:
                raise TLSError("invalid admission reservation")
            if sum(1 for p, pending in self.entries.values() if p == peer) >= 2:
                raise TLSError("peer admission unavailable")
            self.entries[token] = (peer, True)

    def release(self, token):
        with self.lock:
            self.entries.pop(token, None)


_ADMISSION = AdmissionPool()


def _snapshot(value, now):
    """The caller, not a certificate or carrier field, grants enrollment trust."""
    if not isinstance(value, dict) or not math.isfinite(now):
        raise TLSError("trust unavailable")
    names = ("authority_context_id", "local_credential_id", "peer_credential_id",
             "connection_generation", "trust_generation")
    binding = tuple(value.get(name) for name in names)
    if not all(isinstance(item, str) and 0 < len(item) <= 128 for item in binding):
        raise TLSError("invalid binding")
    peer = value.get("peer")
    if not isinstance(peer, dict):
        raise TLSError("trust unavailable")
    key = peer.get("public_key_der")
    if (not isinstance(key, bytes) or len(key) != 91 or
            credential_id_for_public_key(key) != binding[2] or
            peer.get("credential_id") != binding[2] or
            peer.get("authority_context_id") != binding[0] or peer.get("device_kind") != "phone"):
        raise TLSError("peer rejected")
    # No wall-clock timestamp, including a legacy cache's future timestamp,
    # establishes live continuity. The provenance provider must own this exact
    # peer's state; constructing it from a shadow row is not admission.
    from .continuity import BoundContinuity, ContinuityError
    continuity = value.get("continuity")
    if not isinstance(continuity, BoundContinuity):
        raise TLSError("live continuity unavailable")
    try:
        continuity.require_current(binding)
    except ContinuityError:
        raise TLSError("continuity expired") from None
    return binding, key, continuity


class TLSServer(object):
    """Per-stream state; all failures close and release admission immediately.

    receive returns authenticated plaintext only; drain_wire returns ciphertext.
    The owner must cap connections before even assembling a hello (4107 bytes),
    schedule tick at least once per second, and honor outbound backpressure.
    """
    def __init__(self, identity, local_hello, peer_frame, authorization,
                 clock=boottime, wall=time.time, admission=None, admission_token=None):
        self.closed = False
        self.ready = False
        self.token = admission_token
        self.pool = admission if admission is not None else _ADMISSION
        self.clock, self.wall, self.authorization = clock, wall, authorization
        self.created = self.last_clock = clock()
        self.established_at = self.activity = None
        self.header, self.remaining, self.handshake_bytes = bytearray(), 0, 0
        self.handshake_calls = 0
        self.handshake_want_read = 0
        self.incoming = self.outgoing = self.tls = None
        try:
            self.binding, self.key, self.continuity = _snapshot(authorization(), wall())
            if self.token is None:
                self.token = self.pool.acquire(self.binding[2])
            else:
                self.pool.bind(self.token, self.binding[2])
            self.peer = CertificateHello.decode(peer_frame, openssl_path=identity.openssl_path,
                                               lock_path=identity.openssl_lock_path)
            if (local_hello.role != 2 or local_hello.public_key_der != identity.public_key_der or
                    self.binding[1] != identity.credential_id or self.peer.role != 1 or
                    self.peer.public_key_der != self.key):
                raise TLSError("peer rejected")
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.verify_mode = ssl.CERT_REQUIRED
            context.options |= ssl.OP_NO_COMPRESSION
            context.options |= getattr(ssl, "OP_NO_RENEGOTIATION", 0)
            context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
            # Exact enrolled leaf only. These flags never affect Nightscout HTTPS.
            context.verify_flags |= 0x80000 | 0x200000  # PARTIAL_CHAIN, NO_CHECK_TIME
            context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(self.peer.der))
            with tempfile.TemporaryDirectory(prefix="openaps-tls-cert-") as directory:
                path = os.path.join(directory, "local.pem")
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as handle:
                    handle.write(ssl.DER_cert_to_PEM_cert(local_hello.der))
                context.load_cert_chain(path, identity.private_key_path)
            self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
            self.tls = context.wrap_bio(self.incoming, self.outgoing, server_side=True)
            self._check()
        except Exception as error:
            self.close()
            if isinstance(error, TLSError):
                raise
            raise TLSError("TLS admission failed")

    def _check(self, trust=True):
        if self.closed:
            raise TLSError("closed")
        now = self.clock()
        if not math.isfinite(now) or now < self.last_clock:
            raise TLSError("invalid session clock")
        self.last_clock = now
        if not self.ready:
            if now - self.created >= HANDSHAKE_SECONDS:
                raise TLSError("handshake expired")
        elif now - self.established_at >= ABSOLUTE_SECONDS or now - self.activity >= IDLE_SECONDS:
            raise TLSError("session expired")
        if trust and _snapshot(self.authorization(), self.wall()) != (self.binding, self.key, self.continuity):
            raise TLSError("trust changed")
        if self.ready and self.tls.getpeercert(binary_form=True) != self.peer.der:
            raise TLSError("TLS certificate changed")

    def tick(self):
        try:
            self._check()
        except Exception:
            self.close()
            raise TLSError("TLS session unavailable")

    def _wire_bounds(self, data):
        if not isinstance(data, bytes) or len(data) > MAX_WIRE or self.incoming.pending + len(data) > MAX_WIRE:
            raise TLSError("wire limit")
        if not self.ready:
            self.handshake_bytes += len(data)
            if self.handshake_bytes > MAX_WIRE:
                raise TLSError("handshake limit")
        for byte in data:
            if self.remaining:
                self.remaining -= 1
            else:
                self.header.append(byte)
                if len(self.header) == 5:
                    size = self.header[3] * 256 + self.header[4]
                    # TLS 1.2 has no KeyUpdate. Reject subsequent handshake/CCS
                    # records even on older OpenSSL without NO_RENEGOTIATION.
                    if self.ready and self.header[0] not in (21, 23):
                        raise TLSError("post-handshake protocol rejected")
                    if not (20 <= self.header[0] <= 23 and self.header[1] == 3 and
                            self.header[2] <= 3 and 0 < size <= 18432):
                        raise TLSError("record limit")
                    self.remaining = size
                    self.header.clear()

    def receive(self, data):
        try:
            self._check(trust=False)
            self._wire_bounds(data)
            self.incoming.write(data)
            if not self.ready:
                try:
                    self.handshake_calls += 1
                    self.tls.do_handshake()
                except ssl.SSLWantReadError:
                    self.handshake_want_read += 1
                    return self._bounded_result(b"")
                except ssl.SSLWantWriteError:
                    return self._bounded_result(b"")
                self._check()
                if (self.tls.getpeercert(binary_form=True) != self.peer.der or
                        self.tls.version() != "TLSv1.2" or self.tls.cipher()[0] != "ECDHE-ECDSA-AES128-GCM-SHA256"):
                    raise TLSError("TLS peer rejected")
                self.continuity.authenticated_direct_contact(self.binding)
                self.ready = True
                self.established_at = self.activity = self.clock()
                self.pool.established(self.token)
            result = bytearray()
            while True:
                try:
                    chunk = self.tls.read(min(16384, MAX_WIRE + 1 - len(result)))
                except ssl.SSLWantReadError:
                    break
                if not chunk:
                    raise TLSError("peer closed")
                result.extend(chunk)
                if len(result) > MAX_WIRE:
                    raise TLSError("plaintext limit")
            self._check()
            if result:
                self.activity = self.clock()
            return self._bounded_result(bytes(result))
        except Exception as error:
            self.close()
            if isinstance(error, TLSError):
                raise
            if isinstance(error, ssl.SSLError) and getattr(error, "reason", None) == "CERTIFICATE_VERIFY_FAILED":
                raise TLSError("client certificate rejected")
            raise TLSError("TLS input rejected")

    def _bounded_result(self, result):
        if self.outgoing.pending > MAX_PENDING_WIRE:
            raise TLSError("output limit")
        return result

    def write(self, data):
        try:
            self._check()
            if (not self.ready or not isinstance(data, bytes) or not 0 < len(data) <= MAX_WIRE or
                    self.outgoing.pending + len(data) + 2048 > MAX_PENDING_WIRE):
                raise TLSError("application write limit")
            if self.tls.write(data) != len(data):
                raise TLSError("partial application write")
            self._bounded_result(b"")
            self.activity = self.clock()
        except Exception:
            self.close()
            raise TLSError("TLS write rejected")

    def drain_wire(self):
        try:
            self._check(trust=False)
            self._bounded_result(b"")
            return self.outgoing.read(MAX_WIRE)
        except Exception:
            self.close()
            raise TLSError("TLS output unavailable")

    def close(self):
        self.closed, self.ready = True, False
        if self.token is not None:
            self.pool.release(self.token)
            self.token = None
        self.tls = self.incoming = self.outgoing = None
        self.header.clear()
