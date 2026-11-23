"""Nonblocking socket adapter for an admitted TLSStream (Python 3.5).

This takes ownership of one already-accepted socket; it does not listen or
enable a route. A listener must reserve stream admission before spawning work.
Only the stream's authenticated dispatcher may consume decrypted requests.
"""
import select
import socket

from .authorization_tls import TLSError


def serve_tls_socket(connection, stream, cancelled=None, poll=select.select):
    """Run in a bounded connection worker; always close socket and stream.

    At most one 16 KiB write slice leaves the stream queue. No input is read
    until that slice AND the remaining stream output are sent, so copying into
    this adapter cannot enlarge the aggregate application-owned output bound.
    Polling every half-second keeps revocation/deadline checks running even
    while the peer sends nothing or stops reading. The supplied cancellation
    callback must be nonblocking; trust lookup/clinical I/O must also be bounded.
    """
    pending = b""
    try:
        # Kernel buffers are separate from the application-owned queue. Set
        # finite requests explicitly (some kernels account twice this value).
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32768)
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)
        connection.setblocking(False)
        while True:
            if cancelled is not None and cancelled():
                return "cancelled"
            stream.tick()
            if not pending:
                pending = stream.drain(16384)
            readable, writable, exceptional = poll(
                [] if pending else [connection], [connection] if pending else [], [connection], 0.5)
            if exceptional:
                raise TLSError("socket unavailable")
            # Recheck after waiting, before sending queued wire or consuming
            # new input. Never forward bytes after a suspended/expired wait.
            if cancelled is not None and cancelled():
                return "cancelled"
            stream.tick()
            if writable:
                try:
                    sent = connection.send(pending)
                except (BlockingIOError, InterruptedError):
                    continue
                if sent <= 0:
                    raise TLSError("socket write failed")
                pending = pending[sent:]
            elif readable:
                try:
                    wire = connection.recv(16384)
                except (BlockingIOError, InterruptedError):
                    continue
                if not wire:
                    return "eof"
                stream.receive(wire)
    except OSError:
        raise TLSError("socket I/O failed") from None
    finally:
        pending = b""
        try:
            stream.close()
        finally:
            connection.close()


def serve_recovery_socket(connection, stream, cancelled=None, poll=select.select):
    """Own one recovery socket; report termination only after physical close."""
    pending = b""
    result = None
    primary = None
    try:
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32768)
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)
        connection.setblocking(False)
        while True:
            if cancelled is not None and cancelled():
                result = "cancelled"
                break
            stream.tick()
            if not pending:
                pending = stream.drain(16384)
                if not pending and stream.close_required:
                    result = "complete"
                    break
            readable, writable, exceptional = poll(
                [] if pending else [connection], [connection] if pending else [],
                [connection], 0.5)
            if exceptional:
                raise TLSError("socket unavailable")
            if cancelled is not None and cancelled():
                result = "cancelled"
                break
            stream.tick()
            if writable:
                try:
                    sent = connection.send(pending)
                except (BlockingIOError, InterruptedError):
                    continue
                if sent <= 0:
                    raise TLSError("socket write failed")
                pending = pending[sent:]
            elif readable:
                try:
                    wire = connection.recv(16384)
                except (BlockingIOError, InterruptedError):
                    continue
                if not wire:
                    result = "eof"
                    break
                stream.receive(wire)
    except OSError:
        primary = TLSError("socket I/O failed")
    except Exception as exc:
        primary = exc
    finally:
        pending = b""
        try:
            connection.close()
        finally:
            try:
                revision = stream.transport_terminated()
                if result == "complete":
                    result = revision
            except Exception as exc:
                if primary is None:
                    primary = exc
    if primary is not None:
        raise primary
    return result
