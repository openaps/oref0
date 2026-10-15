from __future__ import print_function

import argparse
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid


DEFAULT_ADVERTISE_INTERVAL_MS = 100
HCI_TOOL = "hcitool"
BTMGMT = "btmgmt"
ADVERTISER_HEALTH_INTERVAL_SECONDS = 60
CONTROLLER_COMMAND_TIMEOUT_SECONDS = 5


class HCICommandRejected(RuntimeError):
    def __init__(self, opcode, status):
        self.opcode, self.status = opcode, status
        super(HCICommandRejected, self).__init__(
            "HCI command rejected opcode=0x%04x status=0x%02x" % (opcode, status))


def _validate_hci_command_response(output, expected_opcode):
    # hcitool cmd exits successfully even when the controller rejects its
    # command. It can also receive an unrelated event. Only the matching
    # Command Complete event with success status confirms these commands.
    if not isinstance(output, bytes) or len(output) > 4096:
        raise RuntimeError("invalid HCI command response")
    try:
        text = output.decode("ascii")
    except UnicodeDecodeError:
        raise RuntimeError("invalid HCI command response")
    events = list(re.finditer(r"^> HCI Event: 0x([0-9a-fA-F]{2}) plen ([0-9]+)\s*$",
                              text, re.MULTILINE))
    if len(events) != 1:
        raise RuntimeError("invalid HCI command response")
    event = events[0]
    tokens = text[event.end():].split()
    payload_length = int(event.group(2))
    if (int(event.group(1), 16) != 0x0e or
            not 4 <= payload_length <= 255 or len(tokens) != payload_length or
            any(re.match(r"^[0-9a-fA-F]{2}$", token) is None for token in tokens)):
        raise RuntimeError("invalid HCI command response")
    values = [int(token, 16) for token in tokens]
    opcode = values[1] | (values[2] << 8)
    if opcode != expected_opcode:
        raise RuntimeError("HCI command response opcode mismatch")
    if values[3] != 0:
        raise HCICommandRejected(opcode, values[3])


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _has_established_peripheral_connection(output):
    if not isinstance(output, bytes) or len(output) > 4096:
        return False
    try:
        lines = [line.strip() for line in output.decode("ascii").splitlines() if line.strip()]
    except UnicodeDecodeError:
        return False
    if not lines or lines[0] != "Connections:":
        return False
    peripheral = False
    for line in lines[1:]:
        match = re.match(r"^[<>] LE (?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2} handle ([0-9]+) state ([0-9]+) lm (SLAVE|MASTER)$", line)
        if match is None or not 0 <= int(match.group(1)) <= 4095:
            return False
        peripheral = peripheral or (match.group(2) == "1" and match.group(3) == "SLAVE")
    return peripheral


def _health_path(config):
    explicit = config.get("advertiser_health_path")
    if explicit:
        return explicit
    myopenaps_dir = config.get("myopenaps_dir") or "/root/myopenaps"
    return os.path.join(myopenaps_dir, "openaps-locald-advertiser-health.json")


def _write_health(config, payload):
    path = _health_path(config)
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except OSError:
            pass
    payload = dict(payload)
    payload.setdefault("schema", "openaps.local.ble_advertiser_health.v1")
    payload.setdefault("rig_id", config.get("rig_id"))
    payload["updated_at"] = _utc_now()
    tmp = path + ".new"
    with open(tmp, "w") as f:
        json.dump(payload, f, sort_keys=True, indent=2)
        f.write("\n")
    os.rename(tmp, path)


def _ad_structure(ad_type, payload):
    if not isinstance(payload, (bytes, bytearray)):
        payload = bytes(bytearray(payload))
    if len(payload) > 29:
        raise ValueError("advertising structure payload too large")
    return bytes([len(payload) + 1, ad_type]) + bytes(payload)


def _uuid_to_le_bytes(uuid_text):
    return bytes(bytearray(reversed(uuid.UUID(uuid_text).bytes)))


def build_advertising_data(service_uuid=None, name=None):
    flags = _ad_structure(0x01, b"\x06")
    payload = flags
    if service_uuid:
        payload += _ad_structure(0x07, _uuid_to_le_bytes(service_uuid))
    if name:
        if isinstance(name, bytes):
            name_bytes = name
        else:
            name_bytes = name.encode("utf-8")
        payload += _ad_structure(0x09, name_bytes)
    if len(payload) > 31:
        raise ValueError("advertising data too large")
    return payload + (b"\x00" * (31 - len(payload)))


def build_scan_response_data(name=None, service_uuid=None):
    payload = b""
    if service_uuid:
        payload += _ad_structure(0x07, _uuid_to_le_bytes(service_uuid))
    if name:
        if isinstance(name, bytes):
            name_bytes = name
        else:
            name_bytes = name.encode("utf-8")
        payload += _ad_structure(0x09, name_bytes)
    if len(payload) > 31:
        raise ValueError("scan response data too large")
    return payload + (b"\x00" * (31 - len(payload)))


def _trim_hci_payload(payload):
    end = len(payload)
    while end > 0 and payload[end - 1] == 0:
        end -= 1
    return payload[:end]


def build_advertising_parameters(interval_ms, connectable=True):
    interval_units = int(round(float(interval_ms) / 0.625))
    if interval_units < 0x0020 or interval_units > 0x4000:
        raise ValueError("advertising interval out of range")
    adv_type = 0x00 if connectable else 0x03
    payload = [
        interval_units & 0xFF,
        (interval_units >> 8) & 0xFF,
        interval_units & 0xFF,
        (interval_units >> 8) & 0xFF,
        adv_type,
        0x00,
        0x00,
    ]
    payload.extend([0x00] * 6)
    payload.extend([0x07, 0x00])
    return bytes(payload)


class RawHciAdvertiser(object):
    def __init__(self, config):
        self.config = config
        self.adapter = config.get("advertise_adapter") or config.get("ble_adapter") or "hci0"
        self.name = config.get("ble_name") or "openaps-locald"
        self.restore_name = config.get("rig_id") or self.name
        self.service_uuid = config.get("ble_service_uuid")
        self.interval_ms = int(config.get("advertise_interval_ms") or DEFAULT_ADVERTISE_INTERVAL_MS)
        self.connectable = bool(config.get("advertise_connectable", True))
        self.primary_name = bool(config.get("advertise_primary_name", False))
        self.manage_visibility = bool(config.get("advertise_manage_visibility", True))
        self._running = False
        self._configured = False
        self._enable_pending = False
        self.started_at = None
        self.last_setup_at = None
        self.last_enable_at = None
        self.last_error_at = None
        self.last_error = None

    def _hcitool_command(self, ogf, ocf, params):
        command = [
            HCI_TOOL,
            "-i",
            self.adapter,
            "cmd",
            "0x%02x" % ogf,
            "0x%04x" % ocf,
        ]
        command.extend("0x%02x" % byte for byte in params)
        return command

    def _btmgmt_command(self, *args):
        adapter_index = int(self.config.get("advertise_adapter_index") or 0)
        command = [BTMGMT, "--index", str(adapter_index)]
        command.extend(args)
        return command

    def _ensure_visibility(self):
        if not self.manage_visibility:
            return
        subprocess.check_output(self._btmgmt_command("name", self.name), stderr=subprocess.STDOUT, timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)
        subprocess.check_output(self._btmgmt_command("connectable", "on"), stderr=subprocess.STDOUT, timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)
        subprocess.check_output(self._btmgmt_command("discov", "on"), stderr=subprocess.STDOUT, timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)

    def _restore_visibility(self):
        if not self.manage_visibility:
            return
        try:
            subprocess.check_output(self._btmgmt_command("discov", "off"), stderr=subprocess.STDOUT, timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)
        except Exception:
            pass
        try:
            subprocess.check_output(self._btmgmt_command("connectable", "off"), stderr=subprocess.STDOUT, timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)
        except Exception:
            pass
        try:
            subprocess.check_output(self._btmgmt_command("name", self.restore_name), stderr=subprocess.STDOUT, timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)
        except Exception:
            pass

    def _advertising_pair(self):
        if not self.service_uuid or not self.name:
            return b"", b""
        try:
            combined = _trim_hci_payload(build_advertising_data(service_uuid=self.service_uuid, name=self.name))
        except Exception:
            combined = None
        if combined and len(combined) <= 31:
            return combined, _trim_hci_payload(build_scan_response_data(name=self.name))
        if self.primary_name:
            advertising_data = _trim_hci_payload(build_advertising_data(name=self.name))
            scan_response_data = _trim_hci_payload(build_scan_response_data(service_uuid=self.service_uuid))
        else:
            advertising_data = _trim_hci_payload(build_advertising_data(service_uuid=self.service_uuid))
            scan_response_data = _trim_hci_payload(build_scan_response_data(name=self.name))
        return advertising_data, scan_response_data

    def command_sequence(self):
        advertising_data, scan_response_data = self._advertising_pair()
        # start() has already attempted disable through stop(force=True).
        # Repeating disable can be rejected by an already-disabled controller.
        # Setup and final enable still each require an accepted response.
        return [
            self._hcitool_command(
                0x08,
                0x0006,
                build_advertising_parameters(self.interval_ms, self.connectable),
            ),
            self._hcitool_command(
                0x08,
                0x0008,
                [len(advertising_data)] + list(advertising_data),
            ),
            self._hcitool_command(
                0x08,
                0x0009,
                [len(scan_response_data)] + list(scan_response_data),
            ),
            self._hcitool_command(0x08, 0x000A, [0x01]),
        ]

    def _run_command(self, command):
        # A missing controller reply must not freeze periodic re-enablement or
        # prevent shutdown. check_output kills and reaps a timed-out child.
        output = subprocess.check_output(command, stderr=subprocess.STDOUT,
                                         timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)
        opcode = (int(command[4], 16) << 10) | int(command[5], 16)
        _validate_hci_command_response(output, opcode)

    def start(self):
        self.stop(force=True)
        try:
            self._ensure_visibility()
            commands = self.command_sequence()
            for command in commands[:-1]:
                self._run_command(command)
            self._configured = True
            try:
                self._run_command(commands[-1])
            except HCICommandRejected as exc:
                if exc.opcode != 0x200a or exc.status != 0x0c or not self._established_peripheral_connection():
                    raise
                self._enable_pending = True
                self.last_error_at = _utc_now()
                self.last_error = "enable deferred: established peripheral connection"
        except Exception as exc:
            self.last_error_at = _utc_now()
            self.last_error = "start failed: %s" % exc
            self.stop(force=True)
            raise
        self._running = True
        now = _utc_now()
        self.started_at = now
        self.last_setup_at = now
        if not self._enable_pending:
            self.last_enable_at = now

    def _established_peripheral_connection(self):
        try:
            output = subprocess.check_output([HCI_TOOL, "-i", self.adapter, "con"],
                stderr=subprocess.STDOUT, timeout=CONTROLLER_COMMAND_TIMEOUT_SECONDS)
            return _has_established_peripheral_connection(output)
        except (OSError, ValueError, subprocess.SubprocessError):
            return False

    def stop(self, force=False):
        if not force and not (self._running or self._configured or self._enable_pending):
            return
        try:
            self._run_command(self._hcitool_command(0x08, 0x000A, [0x00]))
        except Exception:
            pass
        try:
            self._restore_visibility()
        except Exception:
            pass
        finally:
            self._running = False
            self._configured = False
            self._enable_pending = False

    def enable_once(self):
        try:
            self._run_command(self._hcitool_command(0x08, 0x000A, [0x01]))
            self.last_enable_at = _utc_now()
            self._enable_pending = False
            return True
        except Exception as exc:
            self.last_error_at = _utc_now()
            self.last_error = str(exc)
            return False

    def health_payload(self, reason):
        advertising_data, scan_response_data = self._advertising_pair()
        return {
            "process": "openaps-locald-advertise",
            "reason": reason,
            "adapter": self.adapter,
            # Lifecycle state only; neither this nor last_enable_at proves
            # that advertisements are currently being transmitted.
            "running": bool(self._running),
            "configured": self._configured,
            "enable_pending": self._enable_pending,
            "started_at": self.started_at,
            "last_setup_at": self.last_setup_at,
            "last_enable_at": self.last_enable_at,
            "last_error_at": self.last_error_at,
            "last_error": self.last_error,
            "service_uuid": self.service_uuid,
            "local_name": self.name,
            "connectable": self.connectable,
            "primary_name": self.primary_name,
            "manage_visibility": self.manage_visibility,
            "advertising_bytes": len(_trim_hci_payload(advertising_data)),
            "scan_response_bytes": len(_trim_hci_payload(scan_response_data)),
        }

    def log_health(self, reason):
        payload = self.health_payload(reason)
        try:
            _write_health(self.config, payload)
        except Exception as exc:
            print("advertiser health write failed error=%s" % exc, flush=True)
        print(
            "advertiser health reason=%s adapter=%s running=%s configured=%s enable_pending=%s service=%s name=%s adv_bytes=%s scan_bytes=%s last_enable=%s error=%s"
            % (
                reason,
                payload.get("adapter"),
                "yes" if payload.get("running") else "no",
                "yes" if payload.get("configured") else "no",
                "yes" if payload.get("enable_pending") else "no",
                payload.get("service_uuid"),
                payload.get("local_name"),
                payload.get("advertising_bytes"),
                payload.get("scan_response_bytes"),
                payload.get("last_enable_at"),
                payload.get("last_error"),
            ),
            flush=True,
        )


def serve_advertiser(config, force=False):
    if not force and not config.get("advertise_enabled"):
        print("advertising disabled by config; exiting")
        return 0
    if not config.get("ble_service_uuid"):
        raise RuntimeError("ble_service_uuid is required for advertising")
    stop_event = threading.Event()
    advertiser = RawHciAdvertiser(config)

    def _stop(*_args):
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    advertiser.start()
    print(
        "started raw HCI advertiser on %s for %s"
        % (advertiser.adapter, advertiser.service_uuid),
        flush=True,
    )
    advertiser.log_health("started")
    last_health = time.time()
    try:
        while not stop_event.wait(2.0):
            # Re-enable advertising every 2 s: the HCI controller automatically
            # disables it when a connection is accepted, so this restores it
            # within 2 s of any disconnection without requiring a service restart.
            advertiser.enable_once()
            if time.time() - last_health >= ADVERTISER_HEALTH_INTERVAL_SECONDS:
                advertiser.log_health("heartbeat")
                last_health = time.time()
    finally:
        advertiser.log_health("stopping")
        advertiser.stop()
    return 0


def build_arg_parser():
    parser = argparse.ArgumentParser(description="OpenAPS local BLE advertiser")
    parser.add_argument("--config", help="Path to openaps-locald JSON config")
    parser.add_argument("--myopenaps-dir", default=None, help="OpenAPS loop directory")
    parser.add_argument("--adapter", default=None, help="Bluetooth adapter name")
    parser.add_argument("--force", action="store_true", help="Start advertising even if config disables it")
    return parser
