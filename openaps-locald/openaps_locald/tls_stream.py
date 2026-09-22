"""Bounded ordered-stream owner shared by future BLE and HTTP adapters.

Adapters serialize calls, schedule tick at least once/second even while idle,
and close on disconnect. They drain only bytes the physical transport accepts;
they must not move the bounded queue into an unbounded external write queue.
No listener is enabled here. The factory supplies provenance-backed admission,
never trust derived from the public certificate hello alone.
"""
import math
import struct

from .authorization_tls import (
    HANDSHAKE_SECONDS, MAX_CERTIFICATE, MAX_PENDING_WIRE, MAX_WIRE,
    TLSError, boottime,
)


class TLSStream(object):
    def __init__(self, local_hello, session_factory, admission, clock=boottime):
        self.pool, self.clock, self.factory = admission, clock, session_factory
        self.closed, self.session, self.token = False, None, None
        self.pending, self.output = bytearray(), bytearray()
        # Payload-free counters used only for bounded relay diagnostics.
        self.input_bytes = 0
        self.output_bytes = 0
        self.handshake_bytes = 0
        self.handshake_calls = 0
        self.handshake_want_read = 0
        self.tls_input_pending = 0
        self.tls_output_pending = 0
        # Only a coarse phase is exposed to the HTTP owner for bounded
        # diagnostics; it never includes payloads or certificate material.
        self.phase = "local_hello"
        self.created = self.last_clock = clock()
        try:
            if not math.isfinite(self.created):
                raise TLSError("invalid stream clock")
            # Reserve before parsing any peer certificate or running OpenSSL.
            self.token = self.pool.acquire(None)
            self.output.extend(local_hello.encode())
            if local_hello.role != 2 or len(self.output) > MAX_CERTIFICATE + 11:
                raise TLSError("invalid local hello")
        except Exception:
            self.close()
            raise

    def close(self):
        self.closed = True
        self.pending.clear()
        self.output.clear()
        try:
            if self.session is not None:
                tls = getattr(self.session, "tls", None)
                if tls is not None:
                    self.handshake_bytes = int(getattr(tls, "handshake_bytes", 0) or 0)
                    self.handshake_calls = int(getattr(tls, "handshake_calls", 0) or 0)
                    self.handshake_want_read = int(getattr(tls, "handshake_want_read", 0) or 0)
                    self.tls_input_pending = int(getattr(getattr(tls, "incoming", None), "pending", 0) or 0)
                    self.tls_output_pending = int(getattr(getattr(tls, "outgoing", None), "pending", 0) or 0)
                self.session.close()
        finally:
            if self.token is not None:
                self.pool.release(self.token)
                self.token = None

    def tick(self):
        try:
            instant = self.clock()
            if self.closed or not math.isfinite(instant) or instant < self.last_clock:
                raise TLSError("invalid stream state")
            self.last_clock = instant
            if (self.session is None or not self.session.tls.ready) and instant - self.created >= HANDSHAKE_SECONDS:
                raise TLSError("stream handshake expired")
            if self.session is not None:
                self.session.tick()
        except Exception:
            self.close()
            raise

    def receive(self, data):
        try:
            self.tick()
            if not isinstance(data, bytes) or len(data) > MAX_WIRE:
                raise TLSError("stream input limit")
            self.input_bytes += len(data)
            if self.session is None:
                # Stage the fixed header first, then only the declared DER.
                take = min(11 - len(self.pending), len(data))
                if take > 0:
                    self.pending.extend(data[:take])
                    data = data[take:]
                if len(self.pending) < 11:
                    return
                size = struct.unpack("!H", bytes(self.pending[9:11]))[0]
                if self.pending[:9] != b"OAPSTLS\x01\x01" or not 0 < size <= MAX_CERTIFICATE:
                    raise TLSError("invalid stream hello")
                take = min(size + 11 - len(self.pending), len(data))
                self.pending.extend(data[:take])
                data = data[take:]
                if len(self.pending) < size + 11:
                    return
                # The factory transfers this reservation into TLSServer rather
                # than acquiring a second slot and extending its rate budget.
                self.session = self.factory(bytes(self.pending), self.token)
                self.pending.clear()
                if self.session.tls.pool is not self.pool or self.session.tls.token is not self.token:
                    raise TLSError("stream admission mismatch")
                self.tick()
                self.phase = "tls_handshake"
            if data:
                wire = self.session.receive(data)
                while wire:
                    if len(self.output) + len(wire) > MAX_PENDING_WIRE:
                        raise TLSError("stream output limit")
                    self.output.extend(wire)
                    # A maximum clinical response plus TLS overhead can exceed
                    # one TLS drain. Collect the remainder under the same cap.
                    wire = self.session.tls.drain_wire()
                if self.session.tls.ready:
                    self.phase = "clinical"
        except Exception:
            self.close()
            raise

    def drain(self, maximum):
        self.tick()
        if not isinstance(maximum, int) or isinstance(maximum, bool) or not 0 < maximum <= MAX_WIRE:
            self.close()
            raise TLSError("invalid stream drain")
        result = bytes(self.output[:maximum])
        del self.output[:maximum]
        self.output_bytes += len(result)
        return result
