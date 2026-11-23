import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from openaps_locald.nightscout_authorization import (
    NightscoutDeviceAuthorizationClient, NightscoutAuthorizationError, URLTransport,
    _RejectRedirects,
)


class EnrollmentAdmissionTests(unittest.TestCase):
    def probe(self, responses, control=(200, {"check": True}), origin="https://example.invalid"):
        client = NightscoutDeviceAuthorizationClient.__new__(NightscoutDeviceAuthorizationClient)
        client.base_url = origin
        authenticated = []
        def request(method, path):
            authenticated.append((method, path))
            return control
        client._authenticated_request = request
        class Anonymous(object):
            def __init__(self):
                self.calls = []
            def request(self, method, path, **kwargs):
                self.calls.append((method, path, kwargs))
                return responses[len(self.calls) - 1]
        anonymous = Anonymous()
        result = client.probe_anonymous_enrollment_write_permissions(anonymous)
        self.assertTrue(all(method == "GET" for method, _ in authenticated))
        self.assertTrue(all(method == "GET" and not kwargs for method, _, kwargs in anonymous.calls))
        return result, anonymous.calls

    def test_all_known_permissions_denied(self):
        result, calls = self.probe([(401, None), (401, None)])
        self.assertIs(result, True)
        self.assertEqual(len(calls), 2)

    def test_public_create_or_socket_write_rejected(self):
        self.assertIs(self.probe([(200, {"check": True})])[0], False)
        self.assertIs(self.probe([(401, None), (200, {"check": True})])[0], False)

    def test_unknown_route_redirect_or_payload_is_inconclusive(self):
        for response in ((404, None), (302, None), (403, None), (200, {"check": False}), (200, {"check": 1})):
            self.assertIsNone(self.probe([response, (401, None)])[0])

    def test_authenticated_control_required(self):
        for control in ((401, None), (200, {}), (200, {"check": 1})):
            result, calls = self.probe([], control=control)
            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_non_https_or_userinfo_refused(self):
        for origin in ("http://example.invalid", "https://placeholder@example.invalid"):
            result, calls = self.probe([], origin=origin)
            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_anonymous_redirect_handler_does_not_follow(self):
        self.assertIsNone(_RejectRedirects().redirect_request(None, None, 302, "redirect", {}, "https://other.invalid"))

    def test_response_read_is_bounded_and_closed(self):
        class Response(io.BytesIO):
            def getcode(self):
                return 200
            def read(self, amount=-1):
                self.amount = amount
                return super(Response, self).read(amount)
        response = Response(b"x" * (1024 * 1024 + 2))
        transport = URLTransport("https://example.invalid", opener=lambda *args, **kwargs: response)
        with self.assertRaises(NightscoutAuthorizationError):
            transport.request("GET", "/synthetic")
        self.assertEqual(response.amount, 1024 * 1024 + 1)
        self.assertTrue(response.closed)

    def test_error_response_is_bounded_and_closed(self):
        stream = io.BytesIO(b"x" * (1024 * 1024 + 2))
        error = HTTPError("https://example.invalid", 401, "synthetic", {}, stream)
        def fail(*args, **kwargs):
            raise error
        with self.assertRaises(NightscoutAuthorizationError):
            URLTransport("https://example.invalid", opener=fail).request("GET", "/synthetic")
        self.assertTrue(stream.closed)

    def test_secure_transport_rejects_unsafe_authority_before_request(self):
        for origin in ("http://example.invalid", "https://placeholder@example.invalid", "https://example.invalid/?token=x",
                       "https://example.invalid/#fragment", "https:///missing"):
            with self.assertRaises(NightscoutAuthorizationError):
                URLTransport(origin, require_https=True, response_limit=8192)
        for limit in (0, True, 1048577):
            with self.assertRaises(NightscoutAuthorizationError):
                URLTransport("https://example.invalid", response_limit=limit)

    def test_secure_transport_preserves_bounded_raw_envelope(self):
        class Response(io.BytesIO):
            def getcode(self):
                return 200
            def read(self, amount=-1):
                self.amount = amount
                return super(Response, self).read(amount)
        # Raw duplicate keys must reach the strict proof parser, not be silently
        # collapsed by the compatibility transport's generic JSON decoder.
        raw = b'{"a":1,"a":2}'
        response = Response(raw)
        calls = []
        def open_response(request, **kwargs):
            calls.append(request)
            return response
        transport = URLTransport("https://example.invalid/base", require_https=True,
                                 response_limit=8192, opener=open_response)
        self.assertEqual(transport.request_bytes("GET", "/api/v3/devicestatus/synthetic", bearer="synthetic"), (200, raw))
        self.assertEqual(response.amount, 8193)
        self.assertTrue(response.closed)
        self.assertEqual(calls[0].full_url, "https://example.invalid/base/api/v3/devicestatus/synthetic")
        self.assertEqual(calls[0].get_header("Authorization"), "Bearer synthetic")

    def test_secure_transport_errors_and_redirects_are_closed(self):
        for status, body in ((302, b""), (307, b"{}"), (401, b"x" * 8193)):
            stream = io.BytesIO(body)
            def fail(*args, **kwargs):
                raise HTTPError("https://example.invalid", status, "synthetic", {}, stream)
            transport = URLTransport("https://example.invalid", require_https=True,
                                     response_limit=8192, opener=fail)
            with self.assertRaises(NightscoutAuthorizationError):
                transport.request_bytes("GET", "/synthetic")
            self.assertTrue(stream.closed)

    def test_secure_transport_installs_redirect_rejection(self):
        with patch("openaps_locald.nightscout_authorization.build_opener") as build:
            transport = URLTransport("https://example.invalid", require_https=True, response_limit=8192)
        self.assertIsInstance(build.call_args[0][0], _RejectRedirects)
        self.assertIs(transport.opener, build.return_value.open)


if __name__ == "__main__":
    unittest.main()
