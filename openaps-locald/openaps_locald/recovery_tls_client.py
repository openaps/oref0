"""Rig-requester restricted MemoryBIO engine, not a physical transport adapter.

transport_terminated is a TRUSTED physical-adapter lifecycle event. MemoryBIO
cannot independently observe a socket closing. The adapter must close its real
transport before delivering that event; timeout/close requests do not release
quota. No production adapter, owner commit, normal renewal or clinical route is
installed here. Completion is engine-owned, never reconstructed from audit data.
"""
import os
import ssl
import struct
import tempfile

from .authorization_tls import TLSError
from .recovery_exchange import RecoveryExchange
from .recovery_tls import ALPN, RecoveryHello, RecoveryReservation, RecoveryTLSServer, _admission
from . import recovery_challenge as codec

_TOKEN = object()


class _Completion:
    def __init__(self, token, engine):
        if token is not _TOKEN:
            raise TLSError("engine completion required")
        self._engine = engine


class RecoveryTLSClient(RecoveryTLSServer):
    """Reuse bounded framing only; deliberately bypass server witness setup."""
    def __init__(self, identity, local_hello, peer_frame, admission, reservation, exchange):
        self.reservation, self.admission, self.identity, self.exchange = reservation, admission, identity, exchange
        self.closed = self.ready = self.responded = self.close_required = False
        self.incoming = self.outgoing = self.tls = None
        self.header, self.pending = bytearray(), bytearray()
        self.remaining = self.received = self.application_received = self.sent = 0
        self._request_sent = self._terminal = False
        self._clean_closed = False
        self._evidence = self._completion = None
        try:
            if not isinstance(reservation, RecoveryReservation) or not isinstance(exchange, RecoveryExchange):
                raise TLSError("concrete recovery owners required")
            reservation.require_held()
            self.binding, self.key = _admission(admission())
            reservation.bind(self.binding[2])
            self._request = exchange.request_data()
            request = codec.decode_request(self._request)
            expected = (self.binding[0], self.binding[1], "rig", self.binding[2], "phone", self.binding[3])
            if tuple(request[k] for k in ("authority_context_id", "requester_credential_id",
                    "requester_device_kind", "witness_credential_id", "witness_device_kind", "connection_id")) != expected:
                raise TLSError("request exchange binding")
            self.peer = RecoveryHello.decode(peer_frame, openssl_path=identity.openssl_path,
                                             lock_path=identity.openssl_lock_path)
            if (not isinstance(local_hello, RecoveryHello) or local_hello.role != 2 or self.peer.role != 1 or
                    local_hello.public_key_der != identity.public_key_der or
                    self.binding[1] != identity.credential_id or self.peer.public_key_der != self.key):
                raise TLSError("recovery requester key or role")
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.verify_mode = ssl.CERT_REQUIRED
            context.options |= ssl.OP_NO_COMPRESSION | getattr(ssl, "OP_NO_RENEGOTIATION", 0)
            context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
            context.set_alpn_protocols([ALPN])
            context.verify_flags |= 0x80000 | 0x200000
            context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(self.peer.der))
            with tempfile.TemporaryDirectory(prefix="synthetic-recovery-requester-cert-") as directory:
                path = os.path.join(directory, "local.pem")
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as handle:
                    handle.write(ssl.DER_cert_to_PEM_cert(local_hello.der))
                context.load_cert_chain(path, identity.private_key_path)
            self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
            self.tls = context.wrap_bio(self.incoming, self.outgoing, server_side=False)
            self._check()
            try:
                self.tls.do_handshake()
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            self._check()
        except Exception:
            self.close()
            raise TLSError("recovery requester setup failed") from None

    def _check(self, admission=True):
        if self.closed:
            raise TLSError("recovery requester closed")
        self.reservation.require_held(self.binding[2])
        if admission and _admission(self.admission()) != (self.binding, self.key):
            raise TLSError("recovery admission changed")
        if self._evidence is None:
            self.exchange.request_data()  # Original suspend-inclusive deadline.
        else:
            self.exchange.current_contact_age(self._evidence)
        if self.ready and (self.tls.getpeercert(binary_form=True) != self.peer.der or
                           self.tls.selected_alpn_protocol() != ALPN):
            raise TLSError("recovery TLS peer changed")

    def receive(self, data):
        try:
            if self._clean_closed and data:
                raise TLSError("bytes after authenticated close")
            if len(data) + self.received + self.sent > 65536:
                raise TLSError("recovery total wire bound")
            super(RecoveryTLSClient, self).receive(data)
            if self.ready and not self._request_sent:
                self._check()
                frame = struct.pack("!I", len(self._request)) + self._request
                if self.tls.write(frame) != len(frame):
                    raise TLSError("recovery request partial write")
                self._request_sent = True
                self._output_bound()
        except Exception:
            self.close()
            raise TLSError("recovery requester input rejected") from None

    def _allow_terminal_input(self):
        return not self._clean_closed

    def _clean_eof(self):
        # SSLObject returns empty only for authenticated TLS close_notify.
        if self._evidence is None:
            if len(self.pending) < 4:
                raise TLSError("close before recovery response")
            count = struct.unpack("!I", bytes(self.pending[:4]))[0]
            if not 0 < count <= 4096 or len(self.pending) != count + 4:
                raise TLSError("incomplete recovery response")
            self._respond()
        if self.remaining or self.header or self.incoming.pending:
            raise TLSError("truncated or trailing TLS records")
        self._clean_closed = True

    def _respond(self):
        if not self._request_sent:
            raise TLSError("unsolicited recovery response")
        self.responded = True
        self._evidence = self.exchange.consume(bytes(self.pending[4:]))
        self.pending.clear()
        self._check()
        self.close_required = True

    def drain_wire(self):
        data = super(RecoveryTLSClient, self).drain_wire()
        self.sent += len(data)
        if self.sent + self.received > 65536:
            self.close()
            raise TLSError("recovery total wire bound")
        return data

    def close(self):
        # Failure/cancellation only. Successful adapter closure follows
        # close_required and reports transport_terminated after actual close.
        self._completion = self._evidence = None
        if isinstance(self.exchange, RecoveryExchange):
            self.exchange.cancel()
        super(RecoveryTLSClient, self).close()

    def transport_terminated(self):
        if self._terminal:
            raise TLSError("terminal event replay")
        self._terminal = True
        try:
            self._check()
            if self.remaining or self.header or self.incoming.pending:
                raise TLSError("incomplete terminal TLS record")
            if not self.responded or self._evidence is None or not self.close_required:
                raise TLSError("recovery incomplete")
            self._completion = _Completion(_TOKEN, self)
            return self._completion
        except Exception:
            self.close()
            raise TLSError("recovery terminal failure") from None
        finally:
            super(RecoveryTLSClient, self).close()
            self.reservation.transport_terminated()

    def require_completion(self, completion):
        if (not self._terminal or completion is None or completion is not self._completion or
                not isinstance(completion, _Completion) or completion._engine is not self or
                _admission(self.admission()) != (self.binding, self.key)):
            raise TLSError("foreign recovery completion")
        self.exchange.current_contact_age(self._evidence)
