"""Bounded loopback relay for the HTTP-owned authorization TLS stream.

This module deliberately has no BlueZ/GATT integration.  It owns only a local
socket and treats every byte after the HTTP Upgrade as opaque transport data.
"""
from __future__ import print_function

import base64
import ipaddress
import json
import socket
import time
try:
    from urllib.parse import urlsplit
except ImportError:
    from urlparse import urlsplit


MAX_UPGRADE_BYTES = 8192
MAX_RELAY_READ_BYTES = 16384
MAX_RECOVERY_PRELUDE_BYTES = 2048


class BLETLSRelayError(Exception):
    pass


def parse_loopback_origin(value):
    """Return (host, port, authority, family) for one explicit HTTP origin.

    Requiring a numeric loopback address prevents this process boundary from
    introducing DNS, redirects, userinfo, or a remotely configurable target.
    """
    if not isinstance(value, str) or not value or value.strip() != value:
        raise BLETLSRelayError("invalid relay origin")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError):
        raise BLETLSRelayError("invalid relay origin")
    if (parsed.scheme != "http" or not parsed.netloc or host is None or
            port is None or port < 1 or parsed.username is not None or parsed.password is not None or
            parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise BLETLSRelayError("invalid relay origin")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise BLETLSRelayError("relay origin must be numeric loopback")
    if not address.is_loopback:
        raise BLETLSRelayError("relay origin must be loopback")
    if address.version == 6:
        authority = "[%s]:%d" % (address.compressed, port)
        family = socket.AF_INET6
    else:
        authority = "%s:%d" % (address.compressed, port)
        family = socket.AF_INET
    return address.compressed, port, authority, family


def _connect_numeric(host, port, family, timeout):
    connection = socket.socket(family, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        address = (host, port, 0, 0) if family == socket.AF_INET6 else (host, port)
        connection.connect(address)
        return connection
    except Exception:
        connection.close()
        raise


class BLETLSRelay(object):
    """One terminal HTTP Upgrade followed by opaque bidirectional bytes."""

    def __init__(self, origin, timeout=5.0, connector=None, monotonic=None,
                 recovery_prelude=None):
        self.host, self.port, self.authority, self.family = parse_loopback_origin(origin)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise BLETLSRelayError("invalid relay timeout")
        self.timeout = float(timeout)
        self.connector = connector or _connect_numeric
        self.monotonic = monotonic or time.monotonic
        self.connection = None
        self._incoming = b""
        self.closed = False
        self.recovery_prelude = None
        if recovery_prelude is not None:
            if (not isinstance(recovery_prelude, bytes) or
                    not 0 < len(recovery_prelude) <= MAX_RECOVERY_PRELUDE_BYTES):
                raise BLETLSRelayError("invalid recovery prelude")
            try:
                fields = json.loads(recovery_prelude.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise BLETLSRelayError("invalid recovery prelude")
            if (not isinstance(fields, dict) or
                    fields.get("schema") != "openaps.http-recovery-prelude.v1" or
                    fields.get("method") != "GET" or
                    fields.get("path") != "/v3/recovery"):
                raise BLETLSRelayError("invalid recovery prelude")
            self.recovery_prelude = recovery_prelude

    def open(self):
        if self.closed or self.connection is not None:
            raise BLETLSRelayError("relay is unavailable")
        try:
            connection = self.connector(
                self.host, self.port, self.family, self.timeout)
            if self.closed:
                connection.close()
                raise BLETLSRelayError("relay is unavailable")
            self.connection = connection
            if self.recovery_prelude is None:
                request = (
                    "GET /v3/tls HTTP/1.1\r\nHost: %s\r\n"
                    "Connection: Upgrade\r\nUpgrade: openaps-tls/1\r\n\r\n"
                ) % self.authority
            else:
                request = (
                    "GET /v3/recovery HTTP/1.1\r\nHost: %s\r\n"
                    "Connection: Upgrade\r\nUpgrade: openaps-recovery/1\r\n"
                    "Content-Length: 0\r\nOpenAPS-Recovery: %s\r\n\r\n"
                ) % (self.authority, base64.b64encode(self.recovery_prelude).decode("ascii"))
            connection.sendall(request.encode("ascii"))
            self._read_upgrade()
            return self
        except BLETLSRelayError:
            self.close()
            raise
        except (OSError, socket.timeout):
            self.close()
            raise BLETLSRelayError("relay connection failed")

    def _read_upgrade(self):
        pending = b""
        deadline = self.monotonic() + self.timeout
        while b"\r\n\r\n" not in pending:
            if len(pending) >= MAX_UPGRADE_BYTES:
                raise BLETLSRelayError("relay upgrade is too large")
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise BLETLSRelayError("relay upgrade timed out")
            self.connection.settimeout(remaining)
            try:
                chunk = self.connection.recv(min(1024, MAX_UPGRADE_BYTES - len(pending)))
            except socket.timeout:
                raise BLETLSRelayError("relay upgrade timed out")
            if not chunk:
                raise BLETLSRelayError("relay upgrade closed")
            pending += chunk
        header, self._incoming = pending.split(b"\r\n\r\n", 1)
        lines = header.split(b"\r\n")
        if not lines or lines[0] != b"HTTP/1.1 101 Switching Protocols":
            raise BLETLSRelayError("relay authorization unavailable")
        fields = {}
        for line in lines[1:]:
            if b":" not in line:
                raise BLETLSRelayError("invalid relay upgrade")
            name, value = line.split(b":", 1)
            try:
                key = name.strip().decode("ascii").lower()
                item = value.strip().decode("ascii").lower()
            except UnicodeDecodeError:
                raise BLETLSRelayError("invalid relay upgrade")
            if not key or key in fields:
                raise BLETLSRelayError("invalid relay upgrade")
            fields[key] = item
        expected_upgrade = "openaps-recovery/1" if self.recovery_prelude is not None else "openaps-tls/1"
        if (set(fields) != set(("connection", "upgrade")) or
                fields.get("connection") != "upgrade" or
                fields.get("upgrade") != expected_upgrade or
                "content-length" in fields or "transfer-encoding" in fields):
            raise BLETLSRelayError("invalid relay upgrade")
        self.connection.settimeout(self.timeout)

    def send(self, data):
        if self.closed or self.connection is None or not isinstance(data, bytes):
            raise BLETLSRelayError("relay is unavailable")
        try:
            self.connection.sendall(data)
        except (OSError, socket.timeout):
            self.close()
            raise BLETLSRelayError("relay write failed")

    def receive(self, maximum=MAX_RELAY_READ_BYTES, timeout=None, timeout_is_empty=False):
        if (self.closed or self.connection is None or not isinstance(maximum, int) or
                maximum < 1 or maximum > MAX_RELAY_READ_BYTES):
            raise BLETLSRelayError("relay is unavailable")
        if self._incoming:
            result, self._incoming = self._incoming[:maximum], self._incoming[maximum:]
            return result
        try:
            if timeout is not None:
                self.connection.settimeout(timeout)
            result = self.connection.recv(maximum)
        except socket.timeout:
            if timeout_is_empty:
                return None
            self.close()
            raise BLETLSRelayError("relay read failed")
        except OSError:
            self.close()
            raise BLETLSRelayError("relay read failed")
        if not result:
            self.close()
            raise BLETLSRelayError("relay closed")
        return result

    def close(self):
        connection, self.connection = self.connection, None
        self._incoming = b""
        self.closed = True
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
