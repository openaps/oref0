from __future__ import print_function

import json
import hashlib
import os
import socket
import subprocess
import signal
import threading
import time
import base64
import math
import uuid
from collections import OrderedDict, deque
try:
    from queue import Empty, Full, Queue
except ImportError:
    from Queue import Empty, Full, Queue
try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen
try:
    from urllib.parse import quote, urlparse
except ImportError:
    from urllib import quote
    from urlparse import urlparse

from .ble_protocol import (
    BLE_ACK_CHAR_UUID,
    BLE_BG_READINGS_CHAR_UUID,
    BLE_DEVICE_STATUS_CHAR_UUID,
    BLE_EVENT_CHAR_UUID,
    BLE_INFO_CHAR_UUID,
    BLE_PUMPHISTORY_CHAR_UUID,
    BLE_SERVICE_UUID,
    BLE_STATUS_CHAR_UUID,
    BLE_TLS_RX_CHAR_UUID,
    BLE_TLS_TX_CHAR_UUID,
    MAX_TLS_RELAY_FRAME_BYTES,
    BleChunkAssembler,
    BleProtocolError,
    decode_ble_payload,
    decode_tls_relay_frame,
    encode_tls_relay_frame,
    payload_to_json_bytes,
)
from .ble_tls_relay import BLETLSRelay, BLETLSRelayError
from .bg_readings import read_bg_readings_payload
from .authorization_protocol import (
    AUTH_ACK_SCHEMA,
    AUTH_HELLO_SCHEMA,
    BLE_AUTH_ATTEMPT_CAPACITY,
    BLE_AUTH_ATTEMPT_REFILL_SECONDS,
    BLE_CREDENTIAL_ATTEMPT_CAPACITY,
    BLE_CREDENTIAL_REFILL_SECONDS,
    BLE_MAX_SESSIONS_GLOBAL,
    BLE_MAX_SESSIONS_PER_CREDENTIAL,
    BLE_UNKNOWN_CREDENTIAL_LIMIT,
    SIGNED_ACK_SCHEMA,
    SIGNED_EVENT_SCHEMA,
    MAX_AUTH_MESSAGE_BYTES,
    MAX_EVENT_MESSAGE_BYTES,
    AuthorizationError,
    ChallengeStore,
    SessionStore,
    TokenBucket,
    build_auth_ack,
    build_shadow_observation,
    build_signed_ack,
    validate_auth_hello_shape,
    validate_signed_event,
    verify_auth_hello,
)
from .authorization_runtime import AuthorizationRuntime
from .config import accepted_patient_ids
from .device_status import read_device_status_payload
from .models import validate_event
from .pump_history import read_pumphistory_payload
from .secure_mode_runtime import SecureModeRouteOwner


try:
    import dbus
    import dbus.service
    import dbus.exceptions
    from dbus.mainloop.glib import DBusGMainLoop
    from dbus.mainloop.glib import threads_init as dbus_threads_init
    from gi.repository import GLib
except Exception:
    dbus = None
    GLib = None


_DBUS_AVAILABLE = dbus is not None
if not _DBUS_AVAILABLE:
    class _UnavailableDBusObject(object):
        pass

    class _UnavailableDBusService(object):
        Object = _UnavailableDBusObject

        @staticmethod
        def method(*_args, **_kwargs):
            return lambda function: function

        @staticmethod
        def signal(*_args, **_kwargs):
            return lambda function: function

    class _UnavailableDBus(object):
        service = _UnavailableDBusService()

    dbus = _UnavailableDBus()


BLUEZ_SERVICE_NAME = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"
BLUEZ_DEVICE_IFACE = "org.bluez.Device1"


class _BoundedWorkerPool(object):
    """Small daemon worker pool with non-blocking, bounded admission."""

    def __init__(self, name, workers, maximum_pending):
        self.name = name
        self.queue = Queue(maxsize=max(1, int(maximum_pending)))
        for index in range(max(1, int(workers))):
            worker = threading.Thread(
                target=self._run,
                name="openaps-%s-%d" % (name, index),
            )
            worker.daemon = True
            worker.start()

    def submit(self, operation):
        try:
            self.queue.put_nowait(operation)
            return True
        except Full:
            return False

    def _run(self):
        while True:
            try:
                operation = self.queue.get()
            except Empty:
                continue
            try:
                operation()
            except Exception as exc:
                _ble_log("%s worker callback failed error=%s" % (self.name, exc))
            finally:
                self.queue.task_done()

def _json_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _matching_legacy_ack_bytes(acks, expected_sha256):
    matches = set()
    for persisted_ack in acks:
        if not isinstance(persisted_ack, dict):
            continue
        encoded = _json_bytes(persisted_ack)
        if hashlib.sha256(encoded).hexdigest() == expected_sha256:
            matches.add(encoded)
    if len(matches) != 1:
        raise AuthorizationError("legacy ACK observation is unavailable or ambiguous")
    return matches.pop()


def _ble_log(message):
    print("[ble] %s" % message, flush=True)


def _event_summary(event):
    if not isinstance(event, dict):
        return "non-dict"
    return "event_id=%s patient_id=%s event_type=%s" % (
        event.get("event_id"),
        event.get("patient_id"),
        event.get("event_type"),
    )


def _ack_summary(ack):
    if not isinstance(ack, dict):
        return "non-dict"
    details = ack.get("details") or {}
    return "event_id=%s ack_status=%s materialization=%s duplicate=%s" % (
        ack.get("event_id"),
        ack.get("ack_status"),
        details.get("materialization"),
        details.get("duplicate"),
    )


def _primary_ipv4_address():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        return None
    finally:
        sock.close()
    return None


def _is_unusable_http_host(host):
    return host in ("", "127.0.0.1", "localhost", "::1", "0.0.0.0", "::")


def _advertised_http_endpoint(config):
    explicit = config.get("ble_advertised_http_base_url") or config.get("advertised_http_base_url")
    if explicit:
        return explicit
    base = config.get("ble_http_base_url") or "http://127.0.0.1:8787"
    parsed = urlparse(base)
    host = parsed.hostname or ""
    if not _is_unusable_http_host(host):
        return base
    ip = _primary_ipv4_address()
    if not ip:
        return base
    port = parsed.port or 8787
    scheme = parsed.scheme or "http"
    return "%s://%s:%s" % (scheme, ip, port)


def _bytes_to_dbus_array(data):
    return dbus.Array([dbus.Byte(b) for b in data], signature="y")


# BlueZ 5.43 on Edison never passes the ATT offset to ReadValue for multi-chunk
# reads — it always calls with options={device: ...} at offset 0 and truncates
# our response to ATT_MTU-1 bytes.  We work around this by caching the full
# payload on the first call and serving sequential ATT-sized chunks on repeated
# calls until the full payload is sent.
_ATT_CHUNK = 184  # ATT_MTU-1 observed on BlueZ 5.43 / Edison BT hardware
_READ_BUFFER_TTL_SECONDS = 5.0
# On the BlueZ version used by the deployed rigs, the write and subsequent
# ReadValue call for one central can be reported with different Device1 paths.
# Keep a freshly verified authorization response available just long enough to
# cross that transport seam.  This is deliberately much shorter than a session
# and is never used for signed event acknowledgements.
_AUTHORIZATION_ACK_HANDOFF_TTL_SECONDS = 15.0
_READ_ENVELOPE_PAYLOAD_BYTES = 36
_BLE_PUMPHISTORY_LIMIT = 24
_BLE_PUMPHISTORY_SAFE_BYTES = 520
_BLE_HEALTH_INTERVAL_SECONDS = 60
# Materializing a just-received BG can invoke the rig's established oref0
# hooks and legitimately take longer than the historical 10-second local HTTP
# request budget. Keep the BLE worker bounded, but leave enough time to return
# the final durable ACK instead of forcing the phone into a duplicate retry.
_BLE_EVENT_POST_TIMEOUT_SECONDS = 20


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _health_path(config):
    explicit = config.get("ble_health_path")
    if explicit:
        return explicit
    myopenaps_dir = config.get("myopenaps_dir") or "/root/myopenaps"
    return os.path.join(myopenaps_dir, "openaps-locald-ble-health.json")


def _write_health(config, payload):
    path = _health_path(config)
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except OSError:
            pass
    payload = dict(payload)
    payload.setdefault("schema", "openaps.local.ble_health.v1")
    payload.setdefault("rig_id", config.get("rig_id"))
    payload["updated_at"] = _utc_now()
    tmp = path + ".new"
    with open(tmp, "w") as f:
        json.dump(payload, f, sort_keys=True, indent=2)
        f.write("\n")
    os.rename(tmp, path)


def _read_envelopes_for_payload(data, characteristic_uuid):
    message_id = "%s-%s" % (characteristic_uuid[-4:], uuid.uuid4().hex)
    total = int(math.ceil(float(len(data)) / float(_READ_ENVELOPE_PAYLOAD_BYTES)))
    envelopes = []
    for seq in range(total):
        chunk = data[seq * _READ_ENVELOPE_PAYLOAD_BYTES : (seq + 1) * _READ_ENVELOPE_PAYLOAD_BYTES]
        envelope = {
            "encoding": "base64",
            "envelope_version": 1,
            "message_id": message_id,
            "payload": base64.b64encode(chunk).decode("ascii"),
            "seq": seq,
            "total": total,
        }
        envelopes.append(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return envelopes


def _dbus_error(name, message):
    return dbus.exceptions.DBusException(message, name=name)


def _bluez_write_error(exc):
    if not _DBUS_AVAILABLE:
        return exc
    if isinstance(exc, dbus.exceptions.DBusException):
        return exc
    return _dbus_error("org.bluez.Error.Failed", str(exc))


class Advertisement(dbus.service.Object):
    def __init__(self, bus, bus_name, index, config):
        self.path = "/com/openaps/locald/advertisement%d" % index
        self.config = config
        self.service_uuids = [config.get("ble_service_uuid") or BLE_SERVICE_UUID]
        self.local_name = config.get("ble_name") or "openaps-locald"
        dbus.service.Object.__init__(self, bus, self.path, bus_name=bus_name)

    def get_properties(self):
        properties = {
            LE_ADVERTISEMENT_IFACE: {
                "Type": "peripheral",
                "ServiceUUIDs": dbus.Array(self.service_uuids, signature="s"),
                "LocalName": dbus.String(self.local_name),
            }
        }
        return properties

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise _dbus_error("org.freedesktop.DBus.Error.InvalidArgs", "invalid interface")
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        return


class LegacyBtMgmtAdvertisement(object):
    def __init__(self, config):
        self.config = config
        self.service_uuid = config.get("ble_service_uuid") or BLE_SERVICE_UUID
        self.local_name = config.get("ble_name") or "openaps-locald"
        self.restore_name = config.get("rig_id") or self.local_name
        self._registered = False

    def _base_cmd(self):
        adapter_index = int(self.config.get("ble_adapter_index") or 0)
        return ["btmgmt", "--index", str(adapter_index)]

    def register(self):
        subprocess.check_call(self._base_cmd() + ["name", self.local_name])
        subprocess.check_call(self._base_cmd() + ["add-uuid", self.service_uuid, "0"])
        subprocess.check_call(self._base_cmd() + ["connectable", "on"])
        subprocess.check_call(self._base_cmd() + ["discov", "on"])
        self._registered = True

    def unregister(self):
        if not self._registered:
            return
        try:
            subprocess.check_call(self._base_cmd() + ["discov", "off"])
            subprocess.check_call(self._base_cmd() + ["rm-uuid", self.service_uuid, "0"])
            subprocess.check_call(self._base_cmd() + ["name", self.restore_name])
        finally:
            self._registered = False


class Application(dbus.service.Object):
    def __init__(self, bus, bus_name, services):
        self.path = "/com/openaps/locald"
        self.services = services
        dbus.service.Object.__init__(self, bus, self.path, bus_name=bus_name)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {}

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()
        return response


class Service(dbus.service.Object):
    def __init__(self, bus, bus_name, index, uuid, primary=True):
        self.path = "/com/openaps/locald/service%d" % index
        self.bus = bus
        self.bus_name = bus_name
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path, bus_name=bus_name)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, chrc):
        self.characteristics.append(chrc)

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise _dbus_error("org.freedesktop.DBus.Error.InvalidArgs", "invalid interface")
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    # Per-device/per-characteristic read buffer: (device_path, characteristic_uuid)
    # -> (envelope_json_chunks, next_index, updated_at). Populated on the first
    # ReadValue call when data exceeds _ATT_CHUNK; consumed across subsequent
    # reads. BlueZ 5.43 on Edison does not pass ATT offsets, so long payloads
    # must be exposed as explicit JSON envelopes rather than raw ATT slices.
    _read_buffers = {}
    _read_buffers_lock = threading.Lock()

    def __init__(self, bus, bus_name, index, uuid, service, flags):
        self.path = service.path + "/char%d" % index
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.notifying = False
        self.value = b""
        dbus.service.Object.__init__(self, bus, self.path, bus_name=bus_name)
        service.add_characteristic(self)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": dbus.Array(self.flags, signature="s"),
                "Value": _bytes_to_dbus_array(self.value),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def _set_value(self, value):
        if isinstance(value, str):
            value = value.encode("utf-8")
        self.value = value
        if self.notifying:
            self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": _bytes_to_dbus_array(self.value)}, [])

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        return

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise _dbus_error("org.freedesktop.DBus.Error.InvalidArgs", "invalid interface")
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        properties = self.GetAll(interface)
        if prop not in properties:
            raise _dbus_error("org.freedesktop.DBus.Error.InvalidArgs", "unknown property")
        return properties[prop]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        device = str(options.get("device", "")) if options else ""
        state_lock = self._read_state_lock(options)
        if state_lock is not None:
            state_lock.acquire()
        try:
            # An ACK characteristic may replace a stale legacy response before
            # it is allowed to serve its per-device chunk cache.  Holding the
            # same lock as ACK publication makes that replacement atomic.
            # A few focused transport harnesses intentionally implement only
            # the read methods they exercise, so keep this hook optional for
            # compatibility with the existing characteristic contract.
            prepare_read = getattr(self, "_prepare_read", None)
            if callable(prepare_read):
                prepare_read(options, device)
            if device:
                key = (device, self.uuid)
                with Characteristic._read_buffers_lock:
                    entry = Characteristic._read_buffers.get(key)
                    if entry is not None:
                        chunks, index, updated_at = entry
                        if time.time() - updated_at > _READ_BUFFER_TTL_SECONDS:
                            Characteristic._read_buffers.pop(key, None)
                            entry = None
                    if entry is not None:
                        chunks, index, _updated_at = entry
                        if index >= len(chunks):
                            Characteristic._read_buffers.pop(key, None)
                        else:
                            chunk = chunks[index]
                            next_index = index + 1
                            if next_index >= len(chunks):
                                Characteristic._read_buffers.pop(key, None)
                            else:
                                Characteristic._read_buffers[key] = (chunks, next_index, time.time())
                            return _bytes_to_dbus_array(chunk)
            data = bytes(bytearray(self._read_value(options)))
            if device and len(data) > _ATT_CHUNK:
                chunks = _read_envelopes_for_payload(data, self.uuid)
                if len(chunks) > 1:
                    with Characteristic._read_buffers_lock:
                        Characteristic._read_buffers[(device, self.uuid)] = (chunks, 1, time.time())
                return _bytes_to_dbus_array(chunks[0])
            return _bytes_to_dbus_array(data)
        finally:
            if state_lock is not None:
                state_lock.release()

    @classmethod
    def clear_read_buffer(cls, device, characteristic_uuid=None):
        if not device:
            return
        with cls._read_buffers_lock:
            if characteristic_uuid is not None:
                cls._read_buffers.pop((device, characteristic_uuid), None)
                return
            for key in [key for key in cls._read_buffers if key[0] == device]:
                cls._read_buffers.pop(key, None)

    @dbus.service.method(
        GATT_CHRC_IFACE,
        in_signature="aya{sv}",
        out_signature="",
        async_callbacks=("reply_handler", "error_handler"),
    )
    def WriteValue(self, value, options, reply_handler, error_handler):
        return self._write_value_async(value, options, reply_handler, error_handler)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="", out_signature="")
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": _bytes_to_dbus_array(self.value)}, [])

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="", out_signature="")
    def StopNotify(self):
        self.notifying = False

    def _read_value(self, options):
        raise _dbus_error("org.bluez.Error.NotPermitted", "read not supported")

    def _read_state_lock(self, options):
        return None

    def _prepare_read(self, options, connection_id):
        return None

    def _write_value(self, value, options):
        raise _dbus_error("org.bluez.Error.NotPermitted", "write not supported")

    def _write_value_async(self, value, options, reply_handler, error_handler):
        try:
            self._write_value(value, options)
            reply_handler()
        except Exception as exc:
            error_handler(_bluez_write_error(exc))


class _BLETLSRelayPending(BLETLSRelayError):
    pass


class _BLETLSRelaySession(object):
    """One bounded worker owns all potentially blocking relay socket I/O."""
    def __init__(self, relay, generation):
        self.relay = relay
        self.generation = generation
        self.outbound = Queue(maxsize=32)
        self.inbound = Queue(maxsize=32)
        # Bounded, payload-free counters make relay failures diagnosable
        # without exposing any TLS bytes or application data in the journal.
        self.socket_send_count = 0
        self.socket_receive_count = 0
        self.closed = threading.Event()
        self.failed = threading.Event()
        self.stopped = threading.Event()
        self.worker = threading.Thread(target=self._run, name="ble-tls-relay")
        self.worker.daemon = True

    def start(self):
        self.worker.start()

    def enqueue(self, value):
        if self.closed.is_set() or self.failed.is_set():
            raise BLETLSRelayError("relay unavailable")
        try:
            self.outbound.put_nowait(value)
        except Full:
            raise BLETLSRelayError("relay outbound queue full")

    def dequeue(self, timeout=None):
        if self.closed.is_set():
            raise BLETLSRelayError("relay unavailable")
        if timeout is None:
            try:
                return self.inbound.get_nowait()
            except Empty:
                if self.failed.is_set():
                    raise BLETLSRelayError("relay unavailable")
                raise _BLETLSRelayPending("relay response unavailable")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise _BLETLSRelayPending("relay response unavailable")
        deadline = time.monotonic() + float(timeout)
        while True:
            if self.closed.is_set():
                raise BLETLSRelayError("relay unavailable")
            try:
                # A recovery peer may close immediately after writing its
                # final TLS flight. Drain already queued bytes before making
                # that EOF terminal to the BLE reader.
                return self.inbound.get_nowait()
            except Empty:
                if self.failed.is_set():
                    raise BLETLSRelayError("relay unavailable")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _BLETLSRelayPending("relay response unavailable")
            try:
                return self.inbound.get(timeout=min(remaining, 0.1))
            except Empty:
                continue

    def _run(self):
        try:
            self.relay.open()
            _ble_log("authorization TLS relay loopback upgraded")
            while not self.closed.is_set():
                try:
                    while True:
                        value = self.outbound.get_nowait()
                        self.relay.send(value)
                        self.socket_send_count += 1
                        if self.socket_send_count <= 40:
                            _ble_log("authorization TLS relay socket tx count=%d bytes=%d" %
                                     (self.socket_send_count, len(value)))
                except Empty:
                    pass
                value = self.relay.receive(
                    MAX_TLS_RELAY_FRAME_BYTES, timeout=0.1, timeout_is_empty=True)
                if value is not None:
                    self.socket_receive_count += 1
                    if self.socket_receive_count <= 40:
                        _ble_log("authorization TLS relay socket rx count=%d bytes=%d" %
                                 (self.socket_receive_count, len(value)))
                    try:
                        self.inbound.put_nowait(value)
                    except Full:
                        raise BLETLSRelayError("relay inbound queue full")
        except Exception as exc:
            if not self.closed.is_set():
                # Keep the diagnostic bounded to an exception class.  Relay
                # errors must never expose endpoint, credential, or clinical
                # data through the BLE service journal.
                _ble_log("authorization TLS relay failed category=%s" %
                         type(exc).__name__)
                self.failed.set()
        finally:
            self.relay.close()
            self.stopped.set()

    def close(self):
        self.closed.set()
        self.relay.close()
        while True:
            try:
                self.outbound.get_nowait()
            except Empty:
                break
        while True:
            try:
                self.inbound.get_nowait()
            except Empty:
                break


class RigBridge(object):
    def __init__(self, config, authorization_runtime=None, monotonic=None,
                 tls_relay_factory=None, secure_mode_policy_provider=None):
        if (secure_mode_policy_provider is not None and
                not callable(secure_mode_policy_provider)):
            raise ValueError("secure mode policy provider must be callable")
        self.config = config
        self.secure_mode_policy_provider = secure_mode_policy_provider
        self.monotonic = monotonic or time.monotonic
        self.assembler = BleChunkAssembler(monotonic=self.monotonic)
        self.http_endpoint = _advertised_http_endpoint(config)
        self.started_at = _utc_now()
        self.last_rig_info_read_at = None
        self.last_status_read_at = None
        self.last_pumphistory_read_at = None
        self.last_device_status_read_at = None
        self.last_bg_readings_read_at = None
        self.last_event_write_at = None
        self.last_event_ack_at = None
        self.last_event_error_at = None
        self.last_event_error = None
        self.last_ack = {
            "ack_status": "idle",
            "details": {},
            "event_id": None,
            "patient_id": config.get("patient_id"),
            "rig_id": config.get("rig_id"),
            "schema": "openaps.local.event_ack.v1",
        }
        self._connection_state_lock = threading.RLock()
        self._acks_by_connection = OrderedDict()
        self._connection_generations = OrderedDict()
        self._connection_generation_counter = 0
        self._authorization_ack_handoff = None
        self._tls_relays_by_connection = {}
        self._tls_relay_factory = tls_relay_factory or BLETLSRelay
        self._tls_relay_enabled = config.get("ble_authorization_tls_relay_enabled") is True
        # Preserve at least one slot in the HTTP owner's two-entry pending TLS
        # handshake pool.  BLE is only a bounded byte carrier and must never be
        # able to monopolize the admission surface, even if a stale deployment
        # requests a larger relay count.
        self._maximum_tls_relays = 1
        self._maximum_connection_states = max(
            8,
            int(config.get("ble_max_connection_states") or 64),
        )
        self._shadow_worker_pool = None
        self._legacy_worker_pool = None
        self.ack_characteristic = None
        self.service_uuid = config.get("ble_service_uuid") or BLE_SERVICE_UUID
        self.authorization = authorization_runtime or AuthorizationRuntime(
            config,
            initialize_in_background=True,
            enable_admission=(config.get("authorization_admission_enabled") is True),
        )
        start_reconciliation = getattr(
            self.authorization,
            "start_periodic_reconciliation",
            None,
        )
        if callable(start_reconciliation):
            start_reconciliation()
        self.authorization_challenges = ChallengeStore(monotonic=self.monotonic)
        self.authorization_sessions = SessionStore(
            monotonic=self.monotonic,
            maximum_per_credential=BLE_MAX_SESSIONS_PER_CREDENTIAL,
            maximum_global=BLE_MAX_SESSIONS_GLOBAL,
        )
        self.authorization_attempts = TokenBucket(
            BLE_AUTH_ATTEMPT_CAPACITY,
            BLE_AUTH_ATTEMPT_REFILL_SECONDS,
            monotonic=self.monotonic,
        )
        self.authorization_credential_attempts = {}
        self.authorization_unknown_credentials = deque()
        self.authorization_failures = {}

    def require_legacy_ble(self, operation):
        """Reject legacy clinical BLE when an explicit policy requires TLS.

        This is an injection seam for the future cross-process supervisor.  No
        provider preserves current compatibility behavior.  A supplied
        unavailable or malformed policy fails closed for the operation.
        """
        if self.secure_mode_policy_provider is None:
            return
        try:
            policy = self.secure_mode_policy_provider()
        except Exception:
            raise BleProtocolError("secure mode unavailable")
        if policy is None:
            raise BleProtocolError("secure mode unavailable")
        if getattr(policy, "state", None) == "disabled":
            return
        if getattr(policy, "state", None) == "ready":
            try:
                blocked = bool(policy.denies_legacy_ble(operation))
            except Exception:
                blocked = True
        else:
            blocked = True
        if blocked:
            raise BleProtocolError("secure mode required")

    def _http_url(self, path):
        base = self.config.get("ble_http_base_url") or "http://127.0.0.1:8787"
        return base.rstrip("/") + path

    def _http_headers(self, content_type=None):
        headers = {}
        token = self.config.get("auth_token")
        if token:
            headers["Authorization"] = "Bearer %s" % token
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _authorize_ble_message(self, message):
        if not self.config.get("ble_require_auth"):
            return
        expected = self.config.get("ble_auth_token")
        if not expected:
            _ble_log("ble auth required but no expected token configured")
            raise BleProtocolError("ble auth required but no auth token configured")
        token = message.get("auth_token")
        if token != expected:
            _ble_log(
                "ble auth failed expected=%s provided=%s"
                % ("yes" if expected else "no", "yes" if token else "no")
            )
            raise BleProtocolError("invalid ble auth token")
        _ble_log("ble auth ok token_present=%s" % ("yes" if token else "no"))

    @staticmethod
    def _credential_hint(value):
        if not isinstance(value, str) or len(value) < 16:
            return "invalid"
        return value[:8] + "..." + value[-8:]

    def _connection_generation(self, connection_id):
        with self._connection_state_lock:
            generation = self._connection_generations.get(connection_id)
            if generation is None:
                self._connection_generation_counter += 1
                generation = self._connection_generation_counter
                self._connection_generations[connection_id] = generation
                while len(self._connection_generations) > self._maximum_connection_states:
                    self._connection_generations.popitem(last=False)
            else:
                self._connection_generations.move_to_end(connection_id)
            return generation

    def _invalidate_connection_generation(self, connection_id):
        with self._connection_state_lock:
            self._connection_generation_counter += 1
            self._connection_generations[connection_id] = self._connection_generation_counter
            self._connection_generations.move_to_end(connection_id)
            while len(self._connection_generations) > self._maximum_connection_states:
                self._connection_generations.popitem(last=False)
            self._acks_by_connection.pop(connection_id, None)
            handoff = self._authorization_ack_handoff
            if handoff is not None and handoff["origin_connection_id"] == connection_id:
                self._authorization_ack_handoff = None

    def clear_connection_state(self, connection_id):
        with self._connection_state_lock:
            relay = self._tls_relays_by_connection.pop(connection_id, None)
        self._invalidate_connection_generation(connection_id)
        self.assembler.clear_connection(connection_id)
        self.authorization_sessions.invalidate_connection(connection_id)
        self.authorization_challenges.remove(connection_id)
        Characteristic.clear_read_buffer(connection_id)
        if relay is not None:
            relay.close()

    def _tls_relay(self, connection_id, create=False):
        if not self._tls_relay_enabled or not connection_id:
            raise BleProtocolError("BLE TLS relay unavailable")
        with self._connection_state_lock:
            relay = self._tls_relays_by_connection.get(connection_id)
            generation = self._connection_generation(connection_id)
            if relay is not None or not create:
                if relay is None:
                    raise BleProtocolError("BLE TLS relay unavailable")
                return relay
            if len(self._tls_relays_by_connection) >= self._maximum_tls_relays:
                raise BleProtocolError("BLE TLS relay busy")
            try:
                transport = self._tls_relay_factory(
                    self.config.get("ble_http_base_url") or "http://127.0.0.1:8787",
                    timeout=min(5.0, max(0.1, float(
                        self.config.get("ble_authorization_tls_relay_timeout") or 5.0))))
            except Exception:
                raise BleProtocolError("BLE TLS relay unavailable")
            relay = _BLETLSRelaySession(transport, generation)
            self._tls_relays_by_connection[connection_id] = relay
            relay.start()
            return relay

    def submit_tls_relay_frame(self, raw_bytes, connection_id):
        payload = decode_tls_relay_frame(raw_bytes)
        relay = self._tls_relay(connection_id, create=True)
        try:
            relay.enqueue(payload)
        except BLETLSRelayError:
            self.clear_connection_state(connection_id)
            raise BleProtocolError("BLE TLS relay unavailable")

    def read_tls_relay_frame(self, connection_id):
        relay = self._tls_relay(connection_id)
        try:
            return encode_tls_relay_frame(relay.dequeue())
        except _BLETLSRelayPending:
            raise BleProtocolError("BLE TLS relay response unavailable")
        except BLETLSRelayError:
            self.clear_connection_state(connection_id)
            raise BleProtocolError("BLE TLS relay unavailable")

    def read_tls_relay_frame_wait(self, connection_id, timeout=7.0):
        """Wait for socket output, or return a transport ACK while pending."""
        relay = self._tls_relay(connection_id)
        try:
            # The phone sends TLS records as several 48-byte ATT writes.  A
            # strict write-then-read exchange would deadlock on every record:
            # the socket cannot answer until its final fragment arrives.  A
            # bounded empty ACK lets the next ATT write proceed; real socket
            # output remains prioritized whenever it is already queued.
            # Keep this aligned with the relay worker's receive cadence.  TLS
            # records commonly span many BLE frames, and the peer cannot
            # answer until the final fragment arrives; waiting a full second
            # after every fragment can consume the entire handshake budget.
            # Once the record is complete the phone's transport polls until
            # the queued response is drained.
            wait = min(float(timeout), 0.1)
            return encode_tls_relay_frame(relay.dequeue(timeout=wait))
        except _BLETLSRelayPending:
            return encode_tls_relay_frame(b"")
        except BLETLSRelayError:
            self.clear_connection_state(connection_id)
            raise BleProtocolError("BLE TLS relay unavailable")

    def handle_device_properties_changed(self, interface, changed, connection_id):
        if interface != BLUEZ_DEVICE_IFACE or not connection_id:
            return False
        if "Connected" not in changed or bool(changed.get("Connected")):
            return False
        self.clear_connection_state(connection_id)
        _ble_log("cleared connection state on disconnect device=%s" % connection_id)
        return True

    def ack_for_connection(self, connection_id):
        with self._connection_state_lock:
            ack = self._acks_by_connection.get(connection_id)
            if ack is None:
                ack = {
                    "ack_status": "idle",
                    "details": {},
                    "event_id": None,
                    "patient_id": self.config.get("patient_id"),
                    "rig_id": self.config.get("rig_id"),
                    "schema": "openaps.local.event_ack.v1",
                }
            else:
                self._acks_by_connection.move_to_end(connection_id)
        return ack

    def prepare_authorization_ack_read(self, connection_id):
        """Bridge the legacy BlueZ write/read Device1 path split once.

        The response is an already signed AUTH_ACK bound to the original
        phone's fresh challenges and session.  Giving it to a different
        ReadValue path cannot authorize that reader or expose a signing key.
        It is nevertheless one-shot, short-lived, and cleared on the writer's
        disconnect so a nearby reader can at most cause a retry, never gain an
        authorization capability.  Signed event ACKs never use this path.
        """
        if not connection_id:
            return False
        now = self.monotonic()
        with self._connection_state_lock:
            handoff = self._authorization_ack_handoff
            if handoff is None:
                return False
            if now - handoff["published_at"] > _AUTHORIZATION_ACK_HANDOFF_TTL_SECONDS:
                self._authorization_ack_handoff = None
                return False
            origin_connection_id = handoff["origin_connection_id"]
            if connection_id == origin_connection_id:
                return False
            if self._connection_generations.get(origin_connection_id) != handoff["origin_generation"]:
                self._authorization_ack_handoff = None
                return False
            existing = self._acks_by_connection.get(connection_id)
            if existing is not None and not (
                existing.get("schema") == "openaps.local.event_ack.v1" and
                existing.get("ack_status") == "idle"
            ):
                return False
            # A read path can still hold chunks from an old legacy ACK.  Clear
            # them before the caller checks its buffer so this signed response
            # is the first and only fresh response it can observe.
            Characteristic.clear_read_buffer(connection_id, BLE_ACK_CHAR_UUID)
            self._acks_by_connection[connection_id] = handoff["ack"]
            self._acks_by_connection.move_to_end(connection_id)
            while len(self._acks_by_connection) > self._maximum_connection_states:
                self._acks_by_connection.popitem(last=False)
            self._authorization_ack_handoff = None
            _ble_log("authorization ack handoff delivered")
            return True

    def _worker_pool(self, shadow):
        with self._connection_state_lock:
            if shadow:
                if self._shadow_worker_pool is None:
                    self._shadow_worker_pool = _BoundedWorkerPool(
                        "ble-shadow",
                        self.config.get("ble_shadow_workers") or 1,
                        self.config.get("ble_shadow_pending") or 4,
                    )
                return self._shadow_worker_pool
            if self._legacy_worker_pool is None:
                self._legacy_worker_pool = _BoundedWorkerPool(
                    "ble-legacy",
                    self.config.get("ble_legacy_workers") or 1,
                    self.config.get("ble_legacy_pending") or 8,
                )
            return self._legacy_worker_pool

    def rig_info_payload(self, connection_id):
        # A rig-info read starts a new BlueZ device-path generation. Treat it as
        # the reconnect boundary available to this bridge and discard any
        # partial messages or authorization state from the prior generation.
        self.clear_connection_state(connection_id)
        payload = {
            "schema": "openaps.local.rig_info.v1",
            "rig_id": self.config.get("rig_id"),
            "patient_id": self.config.get("patient_id"),
            "protocol_version": self.config.get("ble_envelope_version") or 1,
            "service_uuid": self.service_uuid,
            "ble_name": self.config.get("ble_name") or "openaps-locald",
            "http_endpoint": self.http_endpoint,
            "auth_mode": "required" if self.config.get("ble_require_auth") else "dev-only",
            "capabilities": [
                "event_write",
                "status_read",
                "pump_history_read",
                "device_status_read",
                "bg_readings_read",
                "cgm_collector_control",
                "ack_notify",
            ],
        }
        if self._tls_relay_enabled:
            payload["capabilities"].append("authorization_tls_relay_v1")
        # This is a legacy BLE read path. Never take the cross-process trust
        # store flock here; background reconciliation owns cache refreshes.
        carrier_ready = bool(
            self.authorization.identity is not None and
            self.authorization.client is not None and
            getattr(self.authorization, "carrier_ready_cached", False)
        )
        if carrier_ready:
            challenge = self.authorization_challenges.issue(connection_id)
            payload.update({
                "authorization_protocol_version": 1,
                "authorization_credential_id": self.authorization.credential_id,
                "authorization_challenge": challenge,
                "authorization_challenge_expires_in_seconds": 300,
                "authorization_mode": "shadow",
            })
            payload["capabilities"].extend([
                "authorization_shadow",
                "authorization_shadow_nonmutating_v1",
                "signed_event_v2",
            ])
        elif self.authorization.mode == "shadow":
            payload.update({
                "authorization_mode": "shadow_unavailable",
                "authorization_state": self.authorization.last_state.get("classification"),
            })
        return payload

    def _admit_authentication(self, connection_id, credential_id, is_known):
        now = self.monotonic()
        failures = self.authorization_failures.get(connection_id, deque())
        while failures and now - failures[0] >= 300:
            failures.popleft()
        if failures:
            self.authorization_failures[connection_id] = failures
        else:
            self.authorization_failures.pop(connection_id, None)
        if len(failures) >= 3:
            raise AuthorizationError("connection authentication limit reached")
        if not self.authorization_attempts.consume():
            raise AuthorizationError("rig authentication limit reached")
        if not is_known:
            while self.authorization_unknown_credentials and now - self.authorization_unknown_credentials[0][0] >= 300:
                self.authorization_unknown_credentials.popleft()
            known_unknowns = set(item[1] for item in self.authorization_unknown_credentials)
            if credential_id not in known_unknowns:
                if len(known_unknowns) >= BLE_UNKNOWN_CREDENTIAL_LIMIT:
                    raise AuthorizationError("unknown credential limit reached")
                self.authorization_unknown_credentials.append((now, credential_id))
        for stale in [
            key for key, value in self.authorization_credential_attempts.items()
            if now - value.last >= 300
        ]:
            self.authorization_credential_attempts.pop(stale, None)
        bucket = self.authorization_credential_attempts.get(credential_id)
        if bucket is None:
            if len(self.authorization_credential_attempts) >= 128:
                raise AuthorizationError("credential admission table is full")
            bucket = TokenBucket(
                BLE_CREDENTIAL_ATTEMPT_CAPACITY,
                BLE_CREDENTIAL_REFILL_SECONDS,
                monotonic=self.monotonic,
            )
            self.authorization_credential_attempts[credential_id] = bucket
        if not bucket.consume():
            raise AuthorizationError("credential authentication limit reached")

    def _record_authentication_failure(self, connection_id):
        now = self.monotonic()
        failures = self.authorization_failures.setdefault(connection_id, deque())
        while failures and now - failures[0] >= 300:
            failures.popleft()
        failures.append(now)

    def _submit_auth_hello(self, message, connection_id, raw_size, total_chunks):
        if raw_size > MAX_AUTH_MESSAGE_BYTES or total_chunks > 32:
            raise AuthorizationError("auth hello exceeds transport limits")
        if self.authorization.identity is None or self.authorization.client is None:
            raise AuthorizationError("authorization shadow is unavailable")
        # Validate all cheap framing, version, destination, and challenge fields
        # before any Nightscout lookup or OpenSSL verifier work.
        validate_auth_hello_shape(message)
        if message.get("rig_credential_id") != self.authorization.credential_id:
            raise AuthorizationError("auth hello destination mismatch")
        self.authorization_challenges.validate(connection_id, message.get("rig_challenge"))
        credential_id = message.get("phone_credential_id")
        cached_peer = self.authorization.client.trust.peer(credential_id)
        self._admit_authentication(connection_id, credential_id, cached_peer is not None)
        if not self.authorization.ensure_shadow_carrier_ready():
            raise AuthorizationError("authorization shadow carrier is unavailable")
        lookup = self.authorization.lookup_peer(credential_id, "phone")
        peer = lookup.get("peer")
        if lookup.get("classification") not in ("present", "present_cached") or not peer:
            raise AuthorizationError("phone enrollment was not confirmed")
        verify_auth_hello(
            message,
            self.authorization.credential_id,
            peer["public_key_der"],
            self.authorization.identity,
        )
        self.authorization.consume_replay(
            "hello",
            credential_id,
            message.get("message_id"),
        )
        self.authorization_challenges.consume(connection_id, message.get("rig_challenge"))
        session_id = self.authorization_sessions.create(
            credential_id,
            self.authorization.credential_id,
            connection_id=connection_id,
        )
        response = build_auth_ack(self.authorization.identity, message, session_id=session_id)
        self.authorization.client.trust.record_direct_contact(credential_id)
        self.authorization_failures.pop(connection_id, None)
        _ble_log(
            "authorization shadow hello verified phone=%s duplicate=%s"
            % (self._credential_hint(credential_id), lookup.get("duplicate_state"))
        )
        return response

    def _submit_signed_event(self, message, connection_id):
        if self.authorization.identity is None or self.authorization.client is None:
            raise AuthorizationError("authorization shadow is unavailable")
        phone_credential_id = message.get("sender_credential_id")
        if message.get("destination_credential_id") != self.authorization.credential_id:
            raise AuthorizationError("signed event destination mismatch")
        self.authorization_sessions.require(
            message.get("session_id"),
            phone_credential_id,
            self.authorization.credential_id,
            connection_id=connection_id,
            nonce=message.get("message_nonce"),
        )
        public_key_der = self.authorization.identity.load_cached_peer_public_key(phone_credential_id)
        payload_bytes = validate_signed_event(
            message,
            public_key_der,
            self.authorization.identity,
        )
        try:
            event = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:
            raise AuthorizationError("signed event payload is invalid JSON") from exc
        if not isinstance(event, dict) or event.get("event_id") != message.get("message_id"):
            raise AuthorizationError("signed event message identifier mismatch")
        validated = validate_event(event)
        if validated.get("patient_id") not in accepted_patient_ids(self.config):
            raise AuthorizationError("signed event patient is not accepted")
        canonical_event = json.loads(validated["json"])
        legacy_ack_bytes = self._persisted_legacy_observation(
            validated,
            message.get("legacy_ack_sha256"),
        )
        self.authorization.consume_replay(
            "event",
            phone_credential_id,
            validated.get("event_id"),
            ack_digest=message.get("legacy_ack_sha256"),
        )
        observation = build_shadow_observation(
            canonical_event,
            message,
            legacy_ack_bytes,
        )
        self.authorization_sessions.consume_nonce(
            message.get("session_id"),
            phone_credential_id,
            self.authorization.credential_id,
            message.get("message_nonce"),
            connection_id=connection_id,
        )
        ack_bytes = _json_bytes(observation)
        signed_ack = build_signed_ack(
            self.authorization.identity,
            message.get("session_id"),
            phone_credential_id,
            validated.get("event_id"),
            message.get("message_nonce"),
            ack_bytes,
        )
        self.authorization.client.trust.record_direct_contact(phone_credential_id)
        return signed_ack

    def _read_local_json(self, path):
        request = Request(self._http_url(path), headers=self._http_headers())
        response = urlopen(request, timeout=10)
        try:
            data = response.read(MAX_EVENT_MESSAGE_BYTES + 1)
        finally:
            try:
                response.close()
            except Exception:
                pass
        if len(data) > MAX_EVENT_MESSAGE_BYTES:
            raise AuthorizationError("legacy observation response is too large")
        payload = json.loads(data.decode("utf-8"))
        if not isinstance(payload, dict):
            raise AuthorizationError("legacy observation response is invalid")
        return payload

    def _persisted_legacy_observation(self, validated, legacy_ack_sha256):
        event_id = validated.get("event_id")
        encoded_event_id = quote(event_id, safe="")
        persisted_event = self._read_local_json("/v1/events/" + encoded_event_id)
        persisted_validated = validate_event(persisted_event)
        if persisted_validated["json"] != validated.get("json"):
            raise AuthorizationError("signed event does not match persisted legacy event")
        persisted_acks = self._read_local_json(
            "/v1/events/" + encoded_event_id + "/acks"
        ).get("acks")
        if not isinstance(persisted_acks, list):
            raise AuthorizationError("legacy ACK observation is unavailable")
        return _matching_legacy_ack_bytes(persisted_acks, legacy_ack_sha256)

    def post_event(self, event):
        _ble_log("post_event sending %s" % _event_summary(event))
        body = _json_bytes({"events": [event]})
        request = Request(self._http_url("/v1/events"), data=body, headers=self._http_headers("application/json"))
        response = urlopen(request, timeout=_BLE_EVENT_POST_TIMEOUT_SECONDS)
        payload = json.loads(response.read().decode("utf-8"))
        acks = payload.get("acks") or []
        if not acks:
            raise BleProtocolError("missing ack from local daemon")
        _ble_log("post_event ack %s" % _ack_summary(acks[0]))
        return acks[0]

    def _publish_ack(self, ack, connection_id="", expected_generation=None):
        schema = ack.get("schema") if isinstance(ack, dict) else None
        with self._connection_state_lock:
            current_generation = self._connection_generation(connection_id)
            if expected_generation is not None and current_generation != expected_generation:
                return False
            # A prior long ACK may still have unread envelope chunks cached for
            # this stable BlueZ device path. Invalidate them while holding the
            # same state lock used by AckCharacteristic._read_value so a new
            # read cannot repopulate the old value during replacement.
            Characteristic.clear_read_buffer(connection_id, BLE_ACK_CHAR_UUID)
            self._acks_by_connection[connection_id] = ack
            self._acks_by_connection.move_to_end(connection_id)
            while len(self._acks_by_connection) > self._maximum_connection_states:
                self._acks_by_connection.popitem(last=False)
            self.last_ack = ack
            if schema == AUTH_ACK_SCHEMA:
                self._authorization_ack_handoff = {
                    "ack": ack,
                    "origin_connection_id": connection_id,
                    "origin_generation": current_generation,
                    "published_at": self.monotonic(),
                }
            elif (
                self._authorization_ack_handoff is not None and
                self._authorization_ack_handoff["origin_connection_id"] == connection_id
            ):
                # A later result from the same write path supersedes an auth
                # response that has not yet crossed BlueZ's read-path seam.
                self._authorization_ack_handoff = None
        # BlueZ exposes one characteristic Value to every subscriber. Keep
        # legacy notifications for compatibility, but never broadcast the
        # connection-bound authorization handshake or signed observation.
        # Those ACKs are available only through the per-connection ReadValue
        # snapshot above.
        if schema == AUTH_ACK_SCHEMA:
            _ble_log("authorization ack published kind=auth")
        if (
            self.ack_characteristic is not None and
            schema not in (AUTH_ACK_SCHEMA, SIGNED_ACK_SCHEMA)
        ):
            try:
                self.ack_characteristic._set_value(_json_bytes(ack))
            except Exception as exc:
                _ble_log("BLE ACK notification failed error=%s" % exc)
        return True

    def submit_event(self, event):
        return self.post_event(event)

    def _prepare_ble_write(self, raw_bytes, connection_id=""):
        _ble_log("ble write received bytes=%d" % len(raw_bytes))
        decoded = decode_ble_payload(raw_bytes)
        _ble_log(
            "ble write decoded envelope_version=%s seq=%s total=%s auth_token=%s"
            % (
                decoded.get("envelope_version"),
                decoded.get("seq"),
                decoded.get("total"),
                "yes" if decoded.get("auth_token") else "no",
            )
        )
        self._authorize_ble_message(decoded)
        if isinstance(decoded, dict) and decoded.get("schema") == "openaps.local.event.v1":
            _ble_log("ble write direct event %s" % _event_summary(decoded))
            self.require_legacy_ble("event_write")
            return False, lambda: self.submit_event(decoded)
        complete = self.assembler.add(decoded, connection_id=connection_id)
        if complete is None:
            return None
        event = json.loads(complete.decode("utf-8"))
        if not isinstance(event, dict):
            raise BleProtocolError("reassembled BLE event must be a JSON object")
        if event.get("schema") == AUTH_HELLO_SCHEMA:
            def submit_auth_hello():
                try:
                    return self._submit_auth_hello(
                        event,
                        connection_id,
                        len(complete),
                        decoded.get("total"),
                    )
                except Exception:
                    self._record_authentication_failure(connection_id)
                    raise
            return True, submit_auth_hello
        if event.get("schema") == SIGNED_EVENT_SCHEMA:
            self.require_legacy_ble("event_write")
            return True, lambda: self._submit_signed_event(event, connection_id)
        _ble_log("ble write reassembled event %s" % _event_summary(event))
        self.require_legacy_ble("event_write")
        return False, lambda: self.submit_event(event)

    def _execute_prepared_ble_write(self, prepared, connection_id, generation):
        if prepared is None:
            return None
        _shadow, operation = prepared
        ack = operation()
        if ack is not None and not self._publish_ack(
            ack,
            connection_id=connection_id,
            expected_generation=generation,
        ):
            # An auth worker can finish after BlueZ has reported disconnect and
            # after _submit_auth_hello created its session. Never leave that
            # session attached to the stable device path's next generation.
            self.authorization_sessions.invalidate_connection(connection_id)
            raise BleProtocolError("BLE connection changed before ACK publication")
        return ack

    def submit_ble_write(self, raw_bytes, connection_id=""):
        prepared = self._prepare_ble_write(raw_bytes, connection_id=connection_id)
        generation = self._connection_generation(connection_id)
        return self._execute_prepared_ble_write(prepared, connection_id, generation)

    def submit_ble_write_async(self, raw_bytes, connection_id, on_success, on_error):
        try:
            prepared = self._prepare_ble_write(raw_bytes, connection_id=connection_id)
            if prepared is None:
                on_success(None)
                return True
            shadow, _operation = prepared
            generation = self._connection_generation(connection_id)

            def run():
                try:
                    ack = self._execute_prepared_ble_write(
                        prepared,
                        connection_id,
                        generation,
                    )
                except Exception as exc:
                    on_error(exc)
                    return
                on_success(ack)

            if not self._worker_pool(shadow).submit(run):
                raise BleProtocolError(
                    "authorization shadow is busy" if shadow else "legacy BLE delivery is busy"
                )
            return True
        except Exception as exc:
            on_error(exc)
            return False


class RigInfoCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(RigInfoCharacteristic, self).__init__(bus, service.bus_name, index, BLE_INFO_CHAR_UUID, service, ["read"])
        self.bridge = bridge

    def _read_value(self, options):
        self.bridge.last_rig_info_read_at = _utc_now()
        connection_id = str(options.get("device", "")) if options else ""
        print(
            "rig info rig=%s patient=%s http=%s auth=%s"
            % (
                self.bridge.config.get("rig_id"),
                self.bridge.config.get("patient_id"),
                self.bridge.http_endpoint,
                "required" if self.bridge.config.get("ble_require_auth") else "dev-only",
            ),
            flush=True,
        )
        return _bytes_to_dbus_array(_json_bytes(self.bridge.rig_info_payload(connection_id)))


class StatusCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(StatusCharacteristic, self).__init__(bus, service.bus_name, index, BLE_STATUS_CHAR_UUID, service, ["read"])
        self.bridge = bridge
        self._cached = {}

    def _fetch_status(self):
        request = Request(self.bridge._http_url("/v1/status"), headers=self.bridge._http_headers())
        response = urlopen(request, timeout=5)
        self._cached = json.loads(response.read().decode("utf-8"))
        return self._cached

    def _read_value(self, options):
        self.bridge.last_status_read_at = _utc_now()
        self.bridge.require_legacy_ble("status")
        try:
            payload = self._fetch_status()
        except Exception as exc:
            payload = {
                "schema": "openaps.local.status.v1",
                "error": str(exc),
                "cached": self._cached,
            }
        return _bytes_to_dbus_array(_json_bytes(payload))


class PumpHistoryCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(PumpHistoryCharacteristic, self).__init__(bus, service.bus_name, index, BLE_PUMPHISTORY_CHAR_UUID, service, ["read"])
        self.bridge = bridge
        self._cached = {}

    def _fetch_pumphistory(self):
        limit = int(self.bridge.config.get("ble_pumphistory_limit") or _BLE_PUMPHISTORY_LIMIT)
        max_bytes = int(self.bridge.config.get("ble_pumphistory_safe_bytes") or _BLE_PUMPHISTORY_SAFE_BYTES)
        self._cached = read_pumphistory_payload(self.bridge.config, limit=limit, max_bytes=max_bytes)
        return self._cached

    def _read_value(self, options):
        self.bridge.last_pumphistory_read_at = _utc_now()
        self.bridge.require_legacy_ble("pump_history")
        try:
            payload = self._fetch_pumphistory()
        except Exception as exc:
            payload = {
                "schema": "openaps.local.pump_history.v1",
                "error": str(exc),
                "cached": self._cached,
            }
        return _bytes_to_dbus_array(_json_bytes(payload))


class DeviceStatusCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(DeviceStatusCharacteristic, self).__init__(bus, service.bus_name, index, BLE_DEVICE_STATUS_CHAR_UUID, service, ["read"])
        self.bridge = bridge
        self._cached = {}

    def _fetch_device_status(self):
        self._cached = read_device_status_payload(self.bridge.config)
        return self._cached

    def _read_value(self, options):
        self.bridge.last_device_status_read_at = _utc_now()
        self.bridge.require_legacy_ble("device_status")
        try:
            payload = self._fetch_device_status()
        except Exception as exc:
            payload = {
                "schema": "openaps.local.device_status.v1",
                "error": str(exc),
                "cached": self._cached,
            }
        return _bytes_to_dbus_array(_json_bytes(payload))


class BgReadingsCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(BgReadingsCharacteristic, self).__init__(bus, service.bus_name, index, BLE_BG_READINGS_CHAR_UUID, service, ["read"])
        self.bridge = bridge
        self._cached = {}

    def _fetch_bg_readings(self):
        limit = int(self.bridge.config.get("ble_bg_readings_limit") or 3)
        self._cached = read_bg_readings_payload(self.bridge.config, limit=limit)
        return self._cached

    def _read_value(self, options):
        self.bridge.last_bg_readings_read_at = _utc_now()
        self.bridge.require_legacy_ble("bg_readings")
        try:
            payload = self._fetch_bg_readings()
        except Exception as exc:
            payload = {
                "schema": "openaps.local.bg_readings.v1",
                "error": str(exc),
                "cached": self._cached,
            }
        return _bytes_to_dbus_array(_json_bytes(payload))


class AckCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(AckCharacteristic, self).__init__(bus, service.bus_name, index, BLE_ACK_CHAR_UUID, service, ["read", "notify"])
        self.bridge = bridge
        self.bridge.ack_characteristic = self
        self._set_value(_json_bytes(self.bridge.last_ack))

    def _read_value(self, options):
        connection_id = str(options.get("device", "")) if options else ""
        ack = self.bridge.ack_for_connection(connection_id)
        operation = ("authorization_ack" if ack.get("schema") == AUTH_ACK_SCHEMA
                     else "event_ack")
        self.bridge.require_legacy_ble(operation)
        return _bytes_to_dbus_array(_json_bytes(ack))

    def _read_state_lock(self, options):
        return self.bridge._connection_state_lock

    def _prepare_read(self, options, connection_id):
        self.bridge.prepare_authorization_ack_read(connection_id)


class EventWriteCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(EventWriteCharacteristic, self).__init__(bus, service.bus_name, index, BLE_EVENT_CHAR_UUID, service, ["write", "write-without-response"])
        self.bridge = bridge

    def _write_value(self, value, options):
        raw = bytes(bytearray(value))
        connection_id = str(options.get("device", "")) if options else ""
        # Authentication hello frames are bootstrap, not clinical traffic.
        # Clinical event frames are gated after bounded decoding in the bridge.
        self.bridge.last_event_write_at = _utc_now()
        try:
            ack = self.bridge.submit_ble_write(raw, connection_id=connection_id)
            if ack is not None:
                self.bridge.last_event_ack_at = _utc_now()
        except Exception as exc:
            self.bridge.last_event_error_at = _utc_now()
            self.bridge.last_event_error = str(exc)
            _ble_log(
                "ble write failed bytes=%d characteristic=%s error=%s"
                % (len(raw), self.uuid, exc)
            )
            raise

    def _write_value_async(self, value, options, reply_handler, error_handler):
        raw = bytes(bytearray(value))
        connection_id = str(options.get("device", "")) if options else ""
        # Authentication hello frames are bootstrap, not clinical traffic.
        # Clinical event frames are gated after bounded decoding in the bridge.
        self.bridge.last_event_write_at = _utc_now()

        def succeed(ack):
            if ack is not None:
                self.bridge.last_event_ack_at = _utc_now()
            reply_handler()

        def fail(exc):
            self.bridge.last_event_error_at = _utc_now()
            self.bridge.last_event_error = str(exc)
            _ble_log(
                "ble write failed bytes=%d characteristic=%s error=%s"
                % (len(raw), self.uuid, exc)
            )
            error_handler(_bluez_write_error(exc))

        self.bridge.submit_ble_write_async(
            raw,
            connection_id=connection_id,
            on_success=succeed,
            on_error=fail,
        )


class TLSRelayRXCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(TLSRelayRXCharacteristic, self).__init__(bus, service.bus_name, index,
            BLE_TLS_RX_CHAR_UUID, service, ["write", "write-without-response"])
        self.bridge = bridge

    def _write_value(self, value, options):
        connection_id = str(options.get("device", "")) if options else ""
        self.bridge.submit_tls_relay_frame(bytes(bytearray(value)), connection_id)


class TLSRelayTXCharacteristic(Characteristic):
    def __init__(self, bus, index, service, bridge):
        super(TLSRelayTXCharacteristic, self).__init__(bus, service.bus_name, index,
            BLE_TLS_TX_CHAR_UUID, service, ["read"])
        self.bridge = bridge

    # A socket response is inherently asynchronous relative to the ATT read:
    # the RX write first wakes the loopback worker, which may need to complete
    # several network writes before a response exists.  Keep the GLib/D-Bus
    # dispatcher responsive by completing ReadValue from a bounded worker.
    @dbus.service.method(
        GATT_CHRC_IFACE,
        in_signature="a{sv}",
        out_signature="ay",
        async_callbacks=("reply_handler", "error_handler"),
    )
    def ReadValue(self, options, reply_handler, error_handler):
        connection_id = str(options.get("device", "")) if options else ""

        def complete():
            try:
                reply_handler(self.bridge.read_tls_relay_frame_wait(connection_id))
            except Exception as exc:
                error_handler(_bluez_write_error(exc))

        worker = threading.Thread(target=complete, name="ble-tls-relay-read")
        worker.daemon = True
        worker.start()


class LocalBleApplication(object):
    def __init__(self, bus, config, secure_mode_policy_provider=None):
        self.bus = bus
        self.config = config
        self.bus_name = dbus.service.BusName("com.openaps.locald", bus=bus)
        self.bridge = RigBridge(
            config,
            secure_mode_policy_provider=secure_mode_policy_provider,
        )
        service = Service(bus, self.bus_name, 0, BLE_SERVICE_UUID, True)
        self.service = service
        self.info = RigInfoCharacteristic(bus, 0, service, self.bridge)
        self.status = StatusCharacteristic(bus, 1, service, self.bridge)
        self.pumphistory = PumpHistoryCharacteristic(bus, 2, service, self.bridge)
        self.device_status = DeviceStatusCharacteristic(bus, 3, service, self.bridge)
        self.bg_readings = BgReadingsCharacteristic(bus, 4, service, self.bridge)
        self.event = EventWriteCharacteristic(bus, 5, service, self.bridge)
        self.ack = AckCharacteristic(bus, 6, service, self.bridge)
        self.tls_rx = None
        self.tls_tx = None
        if config.get("ble_authorization_tls_relay_enabled") is True:
            self.tls_rx = TLSRelayRXCharacteristic(bus, 7, service, self.bridge)
            self.tls_tx = TLSRelayTXCharacteristic(bus, 8, service, self.bridge)
        self.app = Application(bus, self.bus_name, [service])
        self.advertisement = Advertisement(bus, self.bus_name, 0, config)
        self.legacy_advertisement = LegacyBtMgmtAdvertisement(config)
        self.started_at = _utc_now()
        self.registered_at = None
        self.adapter_path = "/org/bluez/%s" % (self.config.get("ble_adapter") or "hci0")
        self.advertisement_backend = None

    def _call_dbus_async(self, method, *args):
        done = threading.Event()
        outcome = {}

        def _reply(*_reply_args, **_reply_kwargs):
            done.set()

        def _error(exc):
            outcome["exc"] = exc
            done.set()

        method(*args, reply_handler=_reply, error_handler=_error)
        if not done.wait(30):
            raise RuntimeError("timed out waiting for D-Bus registration")
        if "exc" in outcome:
            raise outcome["exc"]

    def _register_advertisement(self):
        if not self.config.get("ble_legacy_advertising", True):
            print(
                "legacy btmgmt advertisement disabled by config; external advertiser owns discovery",
                flush=True,
            )
            return None
        adapter_path = "/org/bluez/%s" % (self.config.get("ble_adapter") or "hci0")
        options = dbus.Dictionary({}, signature="sv")
        try:
            adv_manager = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), LE_ADVERTISING_MANAGER_IFACE)
            self._call_dbus_async(adv_manager.RegisterAdvertisement, self.advertisement.get_path(), options)
            print("registered D-Bus advertisement on %s for %s" % (adapter_path, self.bridge.service_uuid), flush=True)
            return "dbus"
        except dbus.exceptions.DBusException as exc:
            if "UnknownMethod" not in str(exc):
                raise
        self.legacy_advertisement.register()
        print("registered legacy btmgmt advertisement for %s" % (self.bridge.service_uuid,), flush=True)
        return "btmgmt"

    def register(self):
        adapter_path = self.adapter_path
        adapter = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), GATT_MANAGER_IFACE)
        adapter_props = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), DBUS_PROP_IFACE)
        try:
            adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
        except Exception:
            pass
        options = dbus.Dictionary({}, signature="sv")
        self._call_dbus_async(adapter.RegisterApplication, self.app.get_path(), options)
        self.advertisement_backend = self._register_advertisement()
        self.registered_at = _utc_now()
        if self.advertisement_backend == "dbus":
            print("registered BLE app and D-Bus advertisement on %s for %s" % (adapter_path, self.bridge.service_uuid), flush=True)
        elif self.advertisement_backend == "btmgmt":
            print("registered BLE app and legacy btmgmt advertisement on %s for %s" % (adapter_path, self.bridge.service_uuid), flush=True)
        else:
            print(
                "registered BLE app on %s for %s; external advertiser owns discovery"
                % (adapter_path, self.bridge.service_uuid),
                flush=True,
            )

    def _adapter_health(self):
        payload = {}
        try:
            adapter_props = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, self.adapter_path), DBUS_PROP_IFACE)
            props = adapter_props.GetAll("org.bluez.Adapter1")
            for key in ("Address", "Name", "Alias", "Powered", "Discoverable", "Pairable"):
                if key in props:
                    payload[key.lower()] = props[key]
        except Exception as exc:
            payload["error"] = str(exc)
        return payload

    def health_payload(self, bluez_owner=None):
        chars = [chrc.uuid for chrc in self.service.get_characteristics()]
        bridge = self.bridge
        return {
            "process": "openaps-locald-ble",
            "started_at": self.started_at,
            "registered_at": self.registered_at,
            "bluez_owner": bluez_owner,
            "adapter": self.config.get("ble_adapter") or "hci0",
            "adapter_path": self.adapter_path,
            "adapter_state": self._adapter_health(),
            "service_uuid": self.bridge.service_uuid,
            "gatt_registered": bool(self.registered_at),
            "characteristics": chars,
            "characteristic_count": len(chars),
            "advertisement_backend": self.advertisement_backend or "external",
            "advertise_enabled": bool(self.config.get("advertise_enabled")),
            "last_rig_info_read_at": bridge.last_rig_info_read_at,
            "last_status_read_at": bridge.last_status_read_at,
            "last_pumphistory_read_at": bridge.last_pumphistory_read_at,
            "last_device_status_read_at": bridge.last_device_status_read_at,
            "last_bg_readings_read_at": bridge.last_bg_readings_read_at,
            "last_event_write_at": bridge.last_event_write_at,
            "last_event_ack_at": bridge.last_event_ack_at,
            "last_event_error_at": bridge.last_event_error_at,
            "last_event_error": bridge.last_event_error,
            "authorization_mode": bridge.authorization.mode,
            "authorization_state": bridge.authorization.last_state.get("classification"),
            "authorization_credential_available": bridge.authorization.identity is not None,
        }

    def log_health(self, bluez_owner=None, reason="heartbeat"):
        payload = self.health_payload(bluez_owner=bluez_owner)
        payload["reason"] = reason
        try:
            _write_health(self.config, payload)
        except Exception as exc:
            _ble_log("health write failed error=%s" % exc)
        _ble_log(
            "health reason=%s gatt=%s chars=%s adv=%s powered=%s discoverable=%s last_info=%s last_write=%s last_ack=%s"
            % (
                reason,
                "yes" if payload.get("gatt_registered") else "no",
                payload.get("characteristic_count"),
                payload.get("advertisement_backend"),
                payload.get("adapter_state", {}).get("powered"),
                payload.get("adapter_state", {}).get("discoverable"),
                payload.get("last_rig_info_read_at"),
                payload.get("last_event_write_at"),
                payload.get("last_event_ack_at"),
            )
        )


def serve_ble(config):
    if not _DBUS_AVAILABLE or GLib is None:
        raise RuntimeError("dbus and gi are required for BLE support")
    try:
        dbus_threads_init()
    except Exception:
        pass
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    app = LocalBleApplication(bus, config)
    secure_mode_owner = (SecureModeRouteOwner(
        config, app.bridge.authorization, "ble")
        if config.get("authorization_secure_mode_enabled") is True else None)
    if secure_mode_owner is not None:
        app.bridge.secure_mode_policy_provider = secure_mode_owner.policy
        secure_mode_owner.start()
    print("starting BLE sidecar for rig %s" % config.get("rig_id"), flush=True)
    loop = GLib.MainLoop()
    register_error = {}
    bluez_owner_error = {}

    def _stop_loop(*args):
        try:
            loop.quit()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _stop_loop)
    signal.signal(signal.SIGINT, _stop_loop)

    loop_started = threading.Event()

    def _run_loop():
        loop_started.set()
        loop.run()

    loop_thread = threading.Thread(target=_run_loop)
    loop_thread.daemon = True
    loop_thread.start()
    loop_started.wait(1)
    try:
        try:
            app.register()
            try:
                bluez_owner = bus.get_name_owner(BLUEZ_SERVICE_NAME)
            except Exception:
                bluez_owner = None
            app.log_health(bluez_owner=bluez_owner, reason="registered")
        except Exception as exc:
            register_error["exc"] = exc
            print("BLE registration failed: %s" % exc, flush=True)
            raise

        def _heartbeat():
            try:
                bluez_owner = bus.get_name_owner(BLUEZ_SERVICE_NAME)
            except Exception:
                bluez_owner = None
            app.log_health(bluez_owner=bluez_owner, reason="heartbeat")
            return True

        heartbeat_source = GLib.timeout_add_seconds(_BLE_HEALTH_INTERVAL_SECONDS, _heartbeat)

        def _device_properties_changed(interface, changed, _invalidated, device_path=None):
            app.bridge.handle_device_properties_changed(
                str(interface),
                changed,
                str(device_path or ""),
            )

        bus.add_signal_receiver(
            _device_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface=DBUS_PROP_IFACE,
            arg0=BLUEZ_DEVICE_IFACE,
            path_keyword="device_path",
        )

        def _bluez_owner_changed(name, old_owner, new_owner):
            if name != BLUEZ_SERVICE_NAME:
                return
            if old_owner and old_owner != new_owner:
                bluez_owner_error["exc"] = RuntimeError(
                    "BlueZ D-Bus owner changed old=%s new=%s; restarting BLE sidecar"
                    % (old_owner, new_owner)
                )
                try:
                    app.log_health(bluez_owner=new_owner, reason="bluez-owner-changed")
                except Exception:
                    pass
                print(str(bluez_owner_error["exc"]), flush=True)
                _stop_loop()

        bus.add_signal_receiver(
            _bluez_owner_changed,
            signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus",
            arg0=BLUEZ_SERVICE_NAME,
        )
        loop_thread.join()
    finally:
        if secure_mode_owner is not None:
            secure_mode_owner.close()
        try:
            if "heartbeat_source" in locals():
                GLib.source_remove(heartbeat_source)
        except Exception:
            pass
        try:
            app.log_health(reason="stopping")
        except Exception:
            pass
        _stop_loop()
        if loop_thread.is_alive():
            loop_thread.join(1)
        try:
            adapter_path = "/org/bluez/%s" % (config.get("ble_adapter") or "hci0")
            if getattr(app, "advertisement_backend", None) == "dbus":
                adv_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), LE_ADVERTISING_MANAGER_IFACE)
                adv_manager.UnregisterAdvertisement(app.advertisement.get_path())
            elif getattr(app, "advertisement_backend", None) == "btmgmt":
                app.legacy_advertisement.unregister()
        except Exception:
            pass
    if "exc" in register_error:
        raise register_error["exc"]
    if "exc" in bluez_owner_error:
        raise bluez_owner_error["exc"]
