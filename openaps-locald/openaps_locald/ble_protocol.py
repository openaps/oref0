from __future__ import print_function

import base64
import json
import re
import time

from .authorization_protocol import (
    MAX_AUTH_CHUNKS,
    MAX_AUTH_MESSAGE_BYTES,
    MAX_EVENT_CHUNKS,
    MAX_EVENT_MESSAGE_BYTES,
)


EVENT_SCHEMA = "openaps.local.event.v1"
BLE_ENVELOPE_VERSION = 1
BLE_SERVICE_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0001"
BLE_INFO_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0002"
BLE_STATUS_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0003"
BLE_EVENT_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0004"
BLE_ACK_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0005"
BLE_PUMPHISTORY_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0006"
BLE_DEVICE_STATUS_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0007"
BLE_BG_READINGS_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0008"
BLE_TLS_RX_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0009"
BLE_TLS_TX_CHAR_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d000a"
TLS_RELAY_FRAME_SCHEMA = "openaps.ble.tls-frame.v1"
MAX_TLS_RELAY_FRAME_BYTES = 48
BLE_CHARACTERISTIC_UUIDS = [
    BLE_INFO_CHAR_UUID,
    BLE_STATUS_CHAR_UUID,
    BLE_EVENT_CHAR_UUID,
    BLE_ACK_CHAR_UUID,
    BLE_PUMPHISTORY_CHAR_UUID,
    BLE_DEVICE_STATUS_CHAR_UUID,
    BLE_BG_READINGS_CHAR_UUID,
]
BLE_TLS_CHARACTERISTIC_UUIDS = [BLE_TLS_RX_CHAR_UUID, BLE_TLS_TX_CHAR_UUID]
_AUTH_HELLO_SCHEMA_PATTERN = re.compile(
    br'"schema"\s*:\s*"openaps\.ble\.auth-hello\.v1"'
)
_JSON_UNICODE_ESCAPE_PATTERN = re.compile(br'\\u([0-9a-fA-F]{4})')


class BleProtocolError(Exception):
    pass


def encode_tls_relay_frame(payload):
    # Empty payloads are transport acknowledgements emitted only by the rig
    # while a request/response ATT exchange is waiting for socket output.
    if not isinstance(payload, bytes) or len(payload) > MAX_TLS_RELAY_FRAME_BYTES:
        raise BleProtocolError("TLS relay frame is invalid")
    return _json_dumps({
        "payload": base64.b64encode(payload).decode("ascii"),
        "schema": TLS_RELAY_FRAME_SCHEMA,
    })


def decode_tls_relay_frame(raw_bytes):
    if not isinstance(raw_bytes, (bytes, str)) or len(raw_bytes) > 184:
        raise BleProtocolError("TLS relay frame is invalid")
    payload = _json_loads(raw_bytes)
    if (not isinstance(payload, dict) or set(payload) != set(("payload", "schema")) or
            payload.get("schema") != TLS_RELAY_FRAME_SCHEMA or
            not isinstance(payload.get("payload"), str)):
        raise BleProtocolError("TLS relay frame is invalid")
    try:
        decoded = base64.b64decode(payload["payload"].encode("ascii"), validate=True)
    except Exception:
        raise BleProtocolError("TLS relay frame is invalid")
    # Empty phone-originated frames are transport polls.  They are sent only
    # by the relay channel to keep draining queued rig output; the socket
    # worker treats them as a no-op.  Rig TX ACKs use the same empty payload.
    if len(decoded) > MAX_TLS_RELAY_FRAME_BYTES:
        raise BleProtocolError("TLS relay frame is invalid")
    return decoded


def _ensure_bytes(value, encoding="utf-8"):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode(encoding)
    raise BleProtocolError("payload must be bytes or string")


def _json_dumps(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_loads(raw_bytes):
    if isinstance(raw_bytes, bytes):
        text = raw_bytes.decode("utf-8")
    else:
        text = raw_bytes
    try:
        return json.loads(text)
    except Exception as exc:
        raise BleProtocolError("invalid JSON payload") from exc


def _normalize_seq(seq):
    if not isinstance(seq, int):
        raise BleProtocolError("seq must be an integer")
    if seq < 0:
        raise BleProtocolError("seq must be >= 0")
    return seq


def _normalize_total(total):
    if not isinstance(total, int):
        raise BleProtocolError("total must be an integer")
    if total < 1:
        raise BleProtocolError("total must be >= 1")
    return total


def decode_ble_payload(raw_bytes):
    if not isinstance(raw_bytes, (bytes, str)) or len(raw_bytes) > 4096:
        raise BleProtocolError("BLE frame is too large")
    payload = _json_loads(raw_bytes)
    if isinstance(payload, dict) and payload.get("schema") == EVENT_SCHEMA and payload.get("event_id"):
        return payload
    if not isinstance(payload, dict):
        raise BleProtocolError("BLE payload must be a JSON object")
    if "envelope_version" not in payload:
        raise BleProtocolError("BLE payload missing envelope_version")
    if payload["envelope_version"] != BLE_ENVELOPE_VERSION:
        raise BleProtocolError("unsupported envelope_version %s" % payload["envelope_version"])
    if "message_id" not in payload:
        raise BleProtocolError("BLE payload missing message_id")
    if not isinstance(payload["message_id"], str) or not payload["message_id"] or len(payload["message_id"]) > 128:
        raise BleProtocolError("BLE payload message_id is invalid")
    if "seq" not in payload or "total" not in payload:
        raise BleProtocolError("BLE payload missing seq/total")
    if "payload" not in payload:
        raise BleProtocolError("BLE payload missing payload")
    seq = _normalize_seq(payload["seq"])
    total = _normalize_total(payload["total"])
    if seq >= total:
        raise BleProtocolError("seq must be less than total")
    if total > MAX_EVENT_CHUNKS:
        raise BleProtocolError("BLE payload has too many chunks")
    encoding = payload.get("encoding") or "utf8"
    chunk = payload["payload"]
    if encoding == "base64":
        if not isinstance(chunk, str):
            raise BleProtocolError("base64 payload must be a string")
        try:
            decoded = base64.b64decode(chunk.encode("ascii"), validate=True)
        except Exception as exc:
            raise BleProtocolError("invalid base64 payload") from exc
    elif encoding in ("utf8", "utf-8"):
        decoded = _ensure_bytes(chunk)
    else:
        raise BleProtocolError("unsupported encoding %s" % encoding)
    if len(decoded) > 1024:
        raise BleProtocolError("BLE chunk is too large")
    return {
        "envelope_version": BLE_ENVELOPE_VERSION,
        "message_id": payload["message_id"],
        "seq": seq,
        "total": total,
        "payload": decoded,
        "auth_token": payload.get("auth_token"),
    }


class BleChunkAssembler(object):
    def __init__(self, monotonic=None):
        self._messages = {}
        self.monotonic = monotonic or time.monotonic

    def _prune(self):
        now = self.monotonic()
        for key in [key for key, value in self._messages.items() if now - value["updated"] > 300]:
            self._messages.pop(key, None)

    @staticmethod
    def _declares_auth_hello(chunks):
        ordered = b"".join(chunks[index] for index in sorted(chunks))

        def decode_ascii_escape(match):
            codepoint = int(match.group(1), 16)
            if codepoint <= 0x7f:
                return bytes(bytearray([codepoint]))
            return match.group(0)

        normalized = _JSON_UNICODE_ESCAPE_PATTERN.sub(decode_ascii_escape, ordered)
        return _AUTH_HELLO_SCHEMA_PATTERN.search(normalized) is not None

    def clear_connection(self, connection_id):
        for key in [key for key in self._messages if key[0] == connection_id]:
            self._messages.pop(key, None)

    def add(self, envelope, connection_id=""):
        self._prune()
        message_id = envelope["message_id"]
        seq = envelope["seq"]
        total = envelope["total"]
        payload = envelope["payload"]
        key = (connection_id, message_id)
        if total > MAX_EVENT_CHUNKS:
            raise BleProtocolError("BLE payload has too many chunks")
        if key not in self._messages and len(self._messages) >= 8:
            raise BleProtocolError("too many in-flight BLE messages")
        message = self._messages.setdefault(key, {
            "total": total,
            "chunks": {},
            "bytes": 0,
            "auth_hello": False,
            "updated": self.monotonic(),
        })
        if message["total"] != total:
            self._messages.pop(key, None)
            raise BleProtocolError("message %s total changed" % message_id)
        if seq in message["chunks"] and message["chunks"][seq] != payload:
            self._messages.pop(key, None)
            raise BleProtocolError("message %s chunk changed" % message_id)

        candidate_chunks = dict(message["chunks"])
        candidate_chunks[seq] = payload
        candidate_bytes = message["bytes"]
        if seq not in message["chunks"]:
            candidate_bytes += len(payload)
        auth_hello = message["auth_hello"] or self._declares_auth_hello(candidate_chunks)
        maximum_chunks = MAX_AUTH_CHUNKS if auth_hello else MAX_EVENT_CHUNKS
        maximum_bytes = MAX_AUTH_MESSAGE_BYTES if auth_hello else MAX_EVENT_MESSAGE_BYTES
        if total > maximum_chunks:
            self._messages.pop(key, None)
            raise BleProtocolError("authentication message has too many chunks")
        if candidate_bytes > maximum_bytes:
            self._messages.pop(key, None)
            if auth_hello:
                raise BleProtocolError("authentication message is too large")
            raise BleProtocolError("reassembled BLE message is too large")

        message["bytes"] = candidate_bytes
        message["auth_hello"] = auth_hello
        message["chunks"][seq] = payload
        message["updated"] = self.monotonic()
        if len(message["chunks"]) < total:
            return None
        ordered = []
        if 0 in message["chunks"]:
            expected = list(range(total))
        else:
            expected = list(range(1, total + 1))
        for index in expected:
            if index not in message["chunks"]:
                raise BleProtocolError("message %s missing chunk %s" % (message_id, index))
            ordered.append(message["chunks"][index])
        del self._messages[key]
        return b"".join(ordered)


def payload_to_json_bytes(payload):
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return _json_dumps(payload)
