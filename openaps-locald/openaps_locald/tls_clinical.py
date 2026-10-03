"""Transport-independent clinical request framing inside an admitted TLS stream.

Owners provide a TLSServer and shared dispatchers, serialize calls, schedule
tick, and close on disconnect. No listener or legacy-enforcement switch here.
"""
import json
import struct

from .authorization_tls import TLSError


MAX_FRAME = 65532


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate request field")
        result[key] = value
    return result


def _constant(value):
    raise TLSError("non-finite JSON constant")


class TLSClinicalSession(object):
    def __init__(self, tls, events, reads, authenticated_contact=None):
        self.tls, self.events, self.reads = tls, events, reads
        self.authenticated_contact = authenticated_contact
        self.pending = bytearray()

    def tick(self):
        try:
            self.tls.tick()
        except Exception:
            self.close()
            raise

    def close(self):
        self.pending.clear()
        self.tls.close()

    def receive(self, ciphertext):
        try:
            plaintext = self.tls.receive(ciphertext)
            if len(self.pending) + len(plaintext) > MAX_FRAME + 4:
                raise TLSError("application framing limit")
            self.pending.extend(plaintext)
            while len(self.pending) >= 4:
                length = struct.unpack("!I", bytes(self.pending[:4]))[0]
                if not 0 < length <= MAX_FRAME:
                    raise TLSError("application frame limit")
                if len(self.pending) < length + 4:
                    break
                data = bytes(self.pending[4:length + 4])
                del self.pending[:length + 4]
                request = json.loads(data.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
                self._dispatch(request)
            return self.tls.drain_wire()
        except Exception:
            self.close()
            raise

    def _dispatch(self, request):
        fields = {"schema", "request_id", "destination_credential_id", "method", "path", "query", "body"}
        if not isinstance(request, dict) or set(request) != fields or request["schema"] != "openaps.tls.request.v1":
            raise TLSError("invalid clinical request")
        request_id, path, query = request["request_id"], request["path"], request["query"]
        if (not isinstance(request_id, str) or not 0 < len(request_id) <= 128 or
                not isinstance(path, str) or not 0 < len(path) <= 512 or
                not isinstance(query, dict) or len(query) > 8):
            raise TLSError("request shape limit")
        for key, values in query.items():
            if (not isinstance(key, str) or len(key) > 64 or not isinstance(values, list) or
                    not 0 < len(values) <= 8 or
                    not all(isinstance(v, str) and len(v) <= 512 for v in values)):
                raise TLSError("query shape limit")
        def authorize():
            self.tls.tick()
            if not self.tls.ready or request["destination_credential_id"] != self.tls.binding[1]:
                raise TLSError("clinical destination rejected")
        authorize()
        if (path in ("/v1/wifi", "/v1/wifi/scan", "/v1/wifi/networks") and not query and
                (request["method"] == "POST" or
                 (request["method"] == "GET" and request["body"] is None))):
            status, body = self.reads.wifi_authenticated(request["method"], path, request["body"], authorize)
        elif request["method"] == "GET" and request["body"] is None:
            status, body = self.reads.read_authenticated(path, query, authorize)
        elif request["method"] == "POST" and path == "/v1/events" and not query:
            body = request["body"]
            if (not isinstance(body, dict) or set(body) != {"events"} or
                    not isinstance(body["events"], list) or len(body["events"]) > 64):
                raise TLSError("event batch limit")
            status, body = 200, {"acks": self.events.process_authenticated(body["events"], authorize)}
        else:
            status, body = 404, {"error": "not_found"}
        authorize()
        if self.authenticated_contact is not None:
            self.authenticated_contact()
        response = {"schema": "openaps.tls.response.v1", "request_id": request_id,
                    "status": status, "body": body}
        encoded = json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_FRAME:
            raise TLSError("response frame limit")
        self.tls.write(struct.pack("!I", len(encoded)) + encoded)
