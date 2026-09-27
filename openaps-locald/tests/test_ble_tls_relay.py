import base64
import json
import socket
import threading
import unittest

from openaps_locald.ble_tls_relay import (
    BLETLSRelay, BLETLSRelayError, MAX_UPGRADE_BYTES, parse_loopback_origin,
)


class Fixture(object):
    def __init__(self, replies):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.listener.listen(1)
        self.replies = replies
        self.request = b""
        self.received = b""
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    @property
    def origin(self):
        return "http://127.0.0.1:%d" % self.port

    def run(self):
        connection = None
        try:
            connection, _address = self.listener.accept()
            while b"\r\n\r\n" not in self.request:
                self.request += connection.recv(1024)
            for reply in self.replies:
                connection.sendall(reply)
            connection.settimeout(1)
            try:
                self.received = connection.recv(4096)
                if self.received:
                    connection.sendall(b"reply:" + self.received)
            except socket.timeout:
                pass
        finally:
            if connection is not None:
                connection.close()
            self.listener.close()
            self.done.set()


class BLETLSRelayTests(unittest.TestCase):
    def test_origin_requires_explicit_numeric_loopback(self):
        self.assertEqual(parse_loopback_origin("http://127.0.0.1:8787")[:2],
                         ("127.0.0.1", 8787))
        self.assertEqual(parse_loopback_origin("http://[::1]:8787")[2], "[::1]:8787")
        for value in ("http://localhost:8787", "http://192.0.2.1:8787",
                      "https://127.0.0.1:8787", "http://127.0.0.1",
                      "http://127.0.0.1:0",
                      "http://user@127.0.0.1:8787", "http://127.0.0.1:8787/path",
                      "http://127.0.0.1:8787?x=1", " http://127.0.0.1:8787"):
            with self.assertRaises(BLETLSRelayError):
                parse_loopback_origin(value)

    def test_fragmented_upgrade_and_coalesced_opaque_bytes(self):
        fixture = Fixture([
            b"HTTP/1.1 101 Switching Protocols\r\nConnection: Up",
            b"grade\r\nUpgrade: openaps-tls/1\r\n\r\nhello",
        ])
        relay = BLETLSRelay(fixture.origin).open()
        self.addCleanup(relay.close)
        self.assertEqual(relay.receive(2), b"he")
        self.assertEqual(relay.receive(), b"llo")
        relay.send(b"opaque\x00bytes")
        self.assertEqual(relay.receive(), b"reply:opaque\x00bytes")
        self.assertTrue(fixture.done.wait(2))
        self.assertEqual(fixture.received, b"opaque\x00bytes")
        self.assertEqual(fixture.request,
            ("GET /v3/tls HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
             "Connection: Upgrade\r\nUpgrade: openaps-tls/1\r\n\r\n" %
             fixture.port).encode("ascii"))

    def test_503_fails_closed_without_forwarding_body(self):
        fixture = Fixture([b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 6\r\n\r\nsecret"])
        relay = BLETLSRelay(fixture.origin)
        with self.assertRaises(BLETLSRelayError):
            relay.open()
        self.assertTrue(relay.closed)
        self.assertIsNone(relay.connection)

    def test_recovery_uses_only_loopback_with_bounded_signed_prelude(self):
        prelude = json.dumps({
            "schema": "openaps.http-recovery-prelude.v1",
            "method": "GET", "path": "/v3/recovery",
            "signature": "fixture-signature",
        }, sort_keys=True).encode("utf-8")
        fixture = Fixture([
            b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\n"
            b"Upgrade: openaps-recovery/1\r\n\r\nrecovery-hello",
        ])
        relay = BLETLSRelay(fixture.origin, recovery_prelude=prelude).open()
        self.addCleanup(relay.close)
        self.assertEqual(relay.receive(), b"recovery-hello")
        self.assertEqual(fixture.request,
            ("GET /v3/recovery HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
             "Connection: Upgrade\r\nUpgrade: openaps-recovery/1\r\n"
             "Content-Length: 0\r\nOpenAPS-Recovery: %s\r\n\r\n" %
             (fixture.port, base64.b64encode(prelude).decode("ascii"))).encode("ascii"))

    def test_recovery_rejects_invalid_or_oversized_prelude(self):
        for prelude in (b"", b"not-json", b"{" + b"x" * 2048,
                        b'{"schema":"wrong","method":"GET","path":"/v3/recovery"}',
                        b'{"schema":"openaps.http-recovery-prelude.v1",'
                        b'"method":"POST","path":"/v3/recovery"}'):
            with self.assertRaises(BLETLSRelayError):
                BLETLSRelay("http://127.0.0.1:8787", recovery_prelude=prelude)

    def test_recovery_does_not_accept_normal_tls_upgrade(self):
        prelude = (b'{"schema":"openaps.http-recovery-prelude.v1",'
                   b'"method":"GET","path":"/v3/recovery"}')
        fixture = Fixture([b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\n"
                           b"Upgrade: openaps-tls/1\r\n\r\n"])
        with self.assertRaises(BLETLSRelayError):
            BLETLSRelay(fixture.origin, recovery_prelude=prelude).open()

    def test_malformed_and_oversized_upgrade_fail_closed(self):
        malformed = Fixture([b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\n\r\n"])
        with self.assertRaises(BLETLSRelayError):
            BLETLSRelay(malformed.origin).open()
        unexpected = Fixture([b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\n"
                              b"Upgrade: openaps-tls/1\r\nX-Extra: no\r\n\r\n"])
        with self.assertRaises(BLETLSRelayError):
            BLETLSRelay(unexpected.origin).open()
        oversized = Fixture([b"x" * MAX_UPGRADE_BYTES])
        with self.assertRaises(BLETLSRelayError):
            BLETLSRelay(oversized.origin).open()

    def test_timeout_and_close_are_terminal(self):
        fixture = Fixture([])
        relay = BLETLSRelay(fixture.origin, timeout=0.05)
        with self.assertRaises(BLETLSRelayError):
            relay.open()
        self.assertTrue(relay.closed)
        relay.close()
        with self.assertRaises(BLETLSRelayError):
            relay.send(b"later")


if __name__ == "__main__":
    unittest.main()
