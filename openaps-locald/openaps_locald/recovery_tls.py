"""Restricted recovery TLS, never normal TLS, admission, or clinical dispatch.

The physical owner reserves from its shared AdmissionPool before parsing hello,
supplies the original reservation clock instant, calls tick while idle, drains
bounded ciphertext with backpressure, and closes after response drain/failure.
Only physical terminal confirmation releases the externally retained reservation.
No listener, runtime route or clinical operation is installed by this module.
"""
import json
import math
import os
import re
import ssl
import struct
import tempfile
import uuid

from .authorization_tls import CertificateHello, TLSError, boottime
from .device_identity import credential_id_for_public_key
from .continuity import BoundContinuity
from . import recovery_challenge

ALPN = "openaps-recovery/1"


class RecoveryHello(CertificateHello):
    @classmethod
    def decode(cls, frame, **kwargs):
        if (not isinstance(frame, bytes) or not 11 < len(frame) <= 4107 or
                frame[:8] != b"OAPSREC\x01" or
                struct.unpack("!H", frame[9:11])[0] != len(frame) - 11):
            raise TLSError("wrong recovery mode")
        return cls(frame[8], frame[11:], **kwargs)

    def encode(self):
        return b"OAPSREC" + super(RecoveryHello, self).encode()[7:]


class RecoveryReservation(object):
    """Retained shared-pool ticket; resource accounting, never authorization."""
    def __init__(self, pool, token, created, clock=boottime):
        self.pool, self.token, self.created, self.clock = pool, token, created, clock
        self.last, self.invalid = created, False
        self.require_held()

    def require_held(self, peer=None):
        now = self.clock()
        if (self.invalid or isinstance(self.created, bool) or not isinstance(self.created, (int, float)) or
                not math.isfinite(self.created) or self.created < 0 or
                not math.isfinite(now) or now < self.last or now - self.created >= 20):
            self.invalid = True
            raise TLSError("recovery reservation expired")
        self.last = now
        with self.pool.lock:
            entry = self.pool.entries.get(self.token)
            if entry is None or (peer is not None and entry[0] != peer):
                raise TLSError("recovery reservation unavailable")

    def bind(self, peer):
        self.require_held()
        with self.pool.lock:
            entry = self.pool.entries.get(self.token)
        if entry == (None, True):
            self.pool.bind(self.token, peer)
        elif entry != (peer, True):
            raise TLSError("recovery reservation peer mismatch")
        self.require_held(peer)

    def transport_terminated(self):
        """Call only after actual transport termination, never timeout alone."""
        self.invalid = True
        self.pool.release(self.token)


def _admission(value):
    if not isinstance(value, dict):
        raise TLSError("recovery admission unavailable")
    names = ("authority_context_id", "local_credential_id", "peer_credential_id",
             "connection_generation", "trust_generation")
    binding = tuple(value.get(name) for name in names)
    if (not all(isinstance(item, str) for item in binding) or
            not re.fullmatch(r"ns_[0-9a-f]{64}", binding[0]) or
            not all(re.fullmatch(r"[0-9a-f]{64}", item) for item in binding[1:3])):
        raise TLSError("recovery admission scope")
    try:
        if any(str(uuid.UUID(item)) != item for item in binding[3:]):
            raise ValueError()
    except ValueError:
        raise TLSError("recovery admission generation") from None
    peer = value.get("peer")
    if not isinstance(peer, dict):
        raise TLSError("recovery peer unavailable")
    key = peer.get("public_key_der")
    if (not isinstance(key, bytes) or len(key) != 91 or
            credential_id_for_public_key(key) != binding[2] or
            peer.get("credential_id") != binding[2] or
            peer.get("authority_context_id") != binding[0] or peer.get("device_kind") != "phone"):
        raise TLSError("recovery peer rejected")
    return binding, key


class RecoveryTLSServer(object):
    """One request/response; caller-provided admission is never manufactured here.

    Witness must be the admission owner's independently tracked exact-peer
    continuity. No authenticated_direct_contact call occurs in this protocol.
    close_required tells the physical owner to terminate, not upgrade in place.
    close() intentionally does NOT release the retained shared reservation.
    """
    def __init__(self, identity, local_hello, peer_frame, admission, witness, reservation):
        self.reservation, self.admission, self.witness = reservation, admission, witness
        self.identity = identity
        self.closed = self.ready = self.responded = self.close_required = False
        self.incoming = self.outgoing = self.tls = None
        self.header, self.pending = bytearray(), bytearray()
        self.remaining = self.received = self.application_received = 0
        try:
            reservation.require_held()
            self.binding, self.key = _admission(admission())
            reservation.bind(self.binding[2])
            if not isinstance(witness, BoundContinuity):
                raise TLSError("recovery witness unavailable")
            self.peer = RecoveryHello.decode(peer_frame, openssl_path=identity.openssl_path,
                                             lock_path=identity.openssl_lock_path)
            if (not isinstance(local_hello, RecoveryHello) or local_hello.role != 2 or
                    local_hello.public_key_der != identity.public_key_der or
                    self.binding[1] != identity.credential_id or self.peer.role != 1 or
                    self.peer.public_key_der != self.key):
                raise TLSError("recovery key mismatch")
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.verify_mode = ssl.CERT_REQUIRED
            context.options |= ssl.OP_NO_COMPRESSION | getattr(ssl, "OP_NO_RENEGOTIATION", 0)
            context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
            context.set_alpn_protocols([ALPN]) # Unsupported ALPN fails closed.
            context.verify_flags |= 0x80000 | 0x200000
            context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(self.peer.der))
            with tempfile.TemporaryDirectory(prefix="openaps-recovery-cert-") as directory:
                path = os.path.join(directory, "local.pem")
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as handle:
                    handle.write(ssl.DER_cert_to_PEM_cert(local_hello.der))
                context.load_cert_chain(path, identity.private_key_path)
            self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
            self.tls = context.wrap_bio(self.incoming, self.outgoing, server_side=True)
            self._check()
        except Exception:
            self.close()
            raise TLSError("recovery TLS admission failed") from None

    def _check(self, admission=True):
        if self.closed:
            raise TLSError("recovery closed")
        self.reservation.require_held(self.binding[2])
        if admission and _admission(self.admission()) != (self.binding, self.key):
            raise TLSError("recovery admission changed")
        if self.ready and (self.tls.getpeercert(binary_form=True) != self.peer.der or
                           self.tls.selected_alpn_protocol() != ALPN):
            raise TLSError("recovery TLS binding changed")
        if self.responded:
            self.witness.require_current(self.binding)

    def tick(self):
        try:
            self._check()
        except Exception:
            self.close()
            raise TLSError("recovery unavailable") from None

    def receive(self, data):
        try:
            self._check(admission=False)
            if ((self.responded and not self._allow_terminal_input()) or not isinstance(data, bytes) or len(data) > 65536 - self.received or
                    self.incoming.pending + len(data) > 65536):
                raise TLSError("recovery wire limit")
            self.received += len(data)
            for byte in data:
                if self.remaining:
                    self.remaining -= 1
                    continue
                self.header.append(byte)
                if len(self.header) == 5:
                    size = self.header[3] * 256 + self.header[4]
                    if (not 20 <= self.header[0] <= 23 or self.header[1] != 3 or
                            self.header[2] > 3 or not 0 < size <= 18432 or
                            (self.ready and self.header[0] not in (21, 23))):
                        raise TLSError("recovery TLS record limit")
                    self.remaining = size
                    self.header.clear()
            self.incoming.write(data)
            if not self.ready:
                try:
                    self.tls.do_handshake()
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    self._output_bound()
                    return
                self._check()
                if (self.tls.getpeercert(binary_form=True) != self.peer.der or
                        self.tls.selected_alpn_protocol() != ALPN or self.tls.version() != "TLSv1.2" or
                        self.tls.cipher()[0] != "ECDHE-ECDSA-AES128-GCM-SHA256"):
                    raise TLSError("recovery TLS peer rejected")
                self.ready = True
                self.reservation.pool.established(self.reservation.token)
            while True:
                try:
                    part = self.tls.read(4101 - self.application_received)
                except ssl.SSLWantReadError:
                    break
                if not part:
                    self._clean_eof()
                    break
                if self.responded:
                    raise TLSError("trailing recovery application data")
                self.application_received += len(part)
                if self.application_received > 4100:
                    raise TLSError("recovery application limit")
                self.pending.extend(part)
            self._check()
            if len(self.pending) >= 4:
                count = struct.unpack("!I", bytes(self.pending[:4]))[0]
                if not 0 < count <= 4096 or len(self.pending) > count + 4:
                    raise TLSError("recovery frame limit")
                if len(self.pending) == count + 4:
                    self._respond()
            self._output_bound()
        except Exception:
            self.close()
            raise TLSError("recovery input rejected") from None

    def _allow_terminal_input(self):
        return False

    def _clean_eof(self):
        if not self.responded or self.remaining or self.header or self.incoming.pending:
            raise TLSError("recovery peer closed")
        self.close_required = True

    def _respond(self):
        self.responded = True # Bad requests burn this connection as well.
        request = recovery_challenge.decode_request(bytes(self.pending[4:]))
        # Requester-generated wire UUID is signed verbatim for this one request.
        # Rig-local connection_generation is independently frozen by _check;
        # it is not the requester's independently assigned connection UUID.
        expected = (self.binding[0], self.binding[2], "phone", self.binding[1], "rig")
        actual = tuple(request[name] for name in ("authority_context_id", "requester_credential_id",
            "requester_device_kind", "witness_credential_id", "witness_device_kind"))
        if actual != expected:
            raise TLSError("recovery request binding")
        response = self.witness.witness_response(request, self.identity, self.binding)
        self._check()
        encoded = json.dumps(response, sort_keys=True, separators=(",", ":")).encode("ascii")
        if not 0 < len(encoded) <= 4096:
            raise TLSError("recovery response bound")
        frame = struct.pack("!I", len(encoded)) + encoded
        if self.tls.write(frame) != len(frame):
            raise TLSError("recovery response partial write")
        self.pending.clear()

    def _output_bound(self):
        if self.outgoing.pending > 65536:
            raise TLSError("recovery output bound")

    def drain_wire(self):
        try:
            self._check()
            self._output_bound()
            data = self.outgoing.read(65536)
            if self.responded and not self.outgoing.pending:
                self.close_required = True
            return data
        except Exception:
            self.close()
            raise TLSError("recovery output unavailable") from None

    def close(self):
        self.closed, self.ready, self.close_required = True, False, True
        self.tls = self.incoming = self.outgoing = None
        self.pending.clear()
        self.header.clear()
