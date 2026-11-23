"""One restricted rig-requester recovery stream; no clinical dispatcher.

This component has no listener. A physical adapter must call
transport_terminated only after its transport is actually closed. Protocol
failure requests closure but retains the shared admission reservation until
that terminal event.
"""
import math
import struct
import uuid

from .authorization_tls import MAX_CERTIFICATE, MAX_PENDING_WIRE, MAX_WIRE, TLSError
from .recovery_tls import RecoveryHello, RecoveryReservation
from .recovery_tls_client import RecoveryTLSClient


class RecoveryStream(object):
    def __init__(self, registry, identity, local_hello, pool, peer_credential_id,
                 peer_public_key_der, clock):
        self.registry, self.identity, self.local_hello, self.pool = registry, identity, local_hello, pool
        self.peer_credential_id, self.peer_public_key_der = peer_credential_id, peer_public_key_der
        self.clock = clock
        self.closed = self.terminal = False
        self.owner = self.handle = self.attempt = self.engine = None
        self.pending, self.output = bytearray(), bytearray()
        self.created = self.last = clock()
        self.token = self.reservation = None
        try:
            if not math.isfinite(self.created):
                raise TLSError("invalid recovery stream clock")
            self.token = pool.acquire(None)
            self.reservation = RecoveryReservation(pool, self.token, self.created, clock=clock)
            self.owner, self.handle = registry.recovery_required(
                peer_credential_id, peer_public_key_der)
            self.output.extend(local_hello.encode())
            if (not isinstance(local_hello, RecoveryHello) or local_hello.role != 2 or
                    local_hello.public_key_der != identity.public_key_der or
                    len(self.output) > MAX_CERTIFICATE + 11):
                raise TLSError("invalid recovery local hello")
        except Exception:
            self._fail()
            if self.reservation is not None:
                self.reservation.transport_terminated()
                self.reservation = None
            raise

    def _fail(self):
        if self.closed:
            return
        self.closed = True
        self.pending.clear()
        self.output.clear()
        if self.engine is not None:
            self.engine.close()
        if self.owner is not None:
            if self.attempt is not None:
                self.owner.cancel_recovery(self.attempt)
            self.registry.cancel_recovery_owner(self.peer_credential_id, self.owner)

    def tick(self):
        try:
            now = self.clock()
            if (self.closed or not math.isfinite(now) or now < self.last or
                    now - self.created >= 20):
                raise TLSError("recovery stream unavailable")
            self.last = now
            self.reservation.require_held()
            if self.engine is not None:
                self.engine.tick()
        except Exception:
            self._fail()
            raise TLSError("recovery stream unavailable") from None

    def receive(self, data):
        try:
            self.tick()
            if not isinstance(data, bytes) or len(data) > MAX_WIRE:
                raise TLSError("recovery stream input limit")
            if self.engine is None:
                take = min(11 - len(self.pending), len(data))
                if take:
                    self.pending.extend(data[:take]); data = data[take:]
                if len(self.pending) < 11:
                    return
                size = struct.unpack("!H", bytes(self.pending[9:11]))[0]
                if self.pending[:9] != b"OAPSREC\x01\x01" or not 0 < size <= MAX_CERTIFICATE:
                    raise TLSError("invalid recovery stream hello")
                take = min(size + 11 - len(self.pending), len(data))
                self.pending.extend(data[:take]); data = data[take:]
                if len(self.pending) < size + 11:
                    return
                connection = str(uuid.uuid4())
                self.attempt = self.owner.begin_recovery(self.handle, connection)
                self.engine = RecoveryTLSClient(self.identity, self.local_hello,
                    bytes(self.pending), self.attempt.admission, self.reservation,
                    self.attempt.exchange)
                self.pending.clear()
                self._collect(self.engine.drain_wire())
            if data:
                self.engine.receive(data)
                self._collect(self.engine.drain_wire())
        except Exception:
            self._fail()
            raise TLSError("recovery stream input rejected") from None

    def _collect(self, data):
        if len(self.output) + len(data) > MAX_PENDING_WIRE:
            raise TLSError("recovery stream output limit")
        self.output.extend(data)

    def drain(self, maximum):
        self.tick()
        if not isinstance(maximum, int) or isinstance(maximum, bool) or not 0 < maximum <= MAX_WIRE:
            self._fail()
            raise TLSError("invalid recovery stream drain")
        result = bytes(self.output[:maximum])
        del self.output[:maximum]
        return result

    @property
    def close_required(self):
        return self.closed or (self.engine is not None and self.engine.close_required)

    def transport_terminated(self):
        if self.terminal:
            raise TLSError("recovery terminal replay")
        self.terminal = True
        try:
            if (self.closed or self.engine is None or not self.engine.close_required or self.output):
                raise TLSError("recovery stream incomplete")
            completion = self.engine.transport_terminated()
            self.reservation = None
            revision = self.registry.commit_recovery_owner(self.peer_credential_id,
                self.owner, self.attempt, self.engine, completion)
            self.closed = True
            return revision
        except Exception:
            self._fail()
            if self.reservation is not None:
                self.reservation.transport_terminated()
                self.reservation = None
            raise TLSError("recovery terminal rejected") from None
