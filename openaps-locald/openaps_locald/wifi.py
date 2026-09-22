"""Wi-Fi operations available only inside an admitted TLS session.

Use the local supplicant control socket: credentials never enter argv, logs,
the event database, or a shell. Existing profiles are retained for fallback.
"""
import contextlib
import fcntl
import hashlib
import os
import socket
import tempfile
import threading
import time


class WiFiError(Exception):
    def __init__(self, code, status=503):
        super(WiFiError, self).__init__(code)
        self.code, self.status = code, status


class Supplicant(object):
    def __init__(self, path):
        self.path = path

    def command(self, command):
        # A private directory prevents another local user intercepting replies.
        with tempfile.TemporaryDirectory(prefix="locald-wifi-") as directory:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                client.settimeout(2)
                client.bind(os.path.join(directory, "control"))
                client.connect(self.path)
                client.send(command.encode("ascii"))
                reply = client.recv(65536).decode("utf-8", errors="replace").strip()
                if reply.startswith("FAIL") or reply == "UNKNOWN COMMAND":
                    raise WiFiError("supplicant_rejected")
                return reply
            except (OSError, UnicodeError):
                raise WiFiError("supplicant_unavailable")
            finally:
                client.close()


def validate_network(body):
    if not isinstance(body, dict) or set(body) != {"ssid", "security", "password", "hidden"}:
        raise WiFiError("invalid_network", 400)
    ssid, password = body["ssid"], body["password"]
    if (not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32 or
            any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in ssid) or
            type(body["hidden"]) is not bool or not isinstance(password, str)):
        raise WiFiError("invalid_network", 400)
    if body["security"] == "wpa2_personal":
        if not 8 <= len(password) <= 63 or any(not 32 <= ord(c) <= 126 for c in password):
            raise WiFiError("invalid_password", 400)
    elif body["security"] != "open" or password:
        raise WiFiError("unsupported_security", 400)
    return body


def decode_ssid(value):
    # wpa_supplicant uses printf-style byte escaping in SCAN_RESULTS/STATUS.
    data, i = bytearray(), 0
    while i < len(value):
        if value[i:i + 2] == "\\x" and i + 4 <= len(value):
            try:
                data.append(int(value[i + 2:i + 4], 16))
                i += 4
                continue
            except ValueError:
                pass
        escapes = {"\\": b"\\", '"': b'"', "n": b"\n", "r": b"\r", "t": b"\t", "e": b"\x1b"}
        if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in escapes:
            data.extend(escapes[value[i + 1]])
            i += 2
        else:
            data.extend(value[i].encode("utf-8"))
            i += 1
    try:
        return data.decode("utf-8")
    except UnicodeError:
        return None


class WiFiService(object):
    def __init__(self, config, control=None, clock=time.monotonic):
        self.enabled = config.get("wifi_setup_enabled", True) is True
        self.control = control or Supplicant(config.get("wifi_control_socket", "/var/run/wpa_supplicant/wlan0"))
        self.lock_path = config.get("wifi_lock_path", "/run/openaps-locald-wifi.lock")
        self.lock = threading.Lock()
        self.clock, self.last_scan = clock, None

    @contextlib.contextmanager
    def serialized(self):
        if not self.enabled:
            raise WiFiError("wifi_setup_disabled", 503)
        if not self.lock.acquire(False):
            raise WiFiError("wifi_busy", 409)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise WiFiError("wifi_busy", 409)
                yield
        except OSError:
            raise WiFiError("wifi_unavailable")
        finally:
            self.lock.release()

    def request(self, method, path, body, authorize):
        # Called only by TLSClinicalSession; never exposed to legacy HTTP/BLE.
        with self.serialized():
            authorize()
            if method == "GET" and path == "/v1/wifi":
                fields = dict(line.split("=", 1) for line in self.control.command("STATUS").splitlines() if "=" in line)
                result = {"schema": "openaps.wifi.status.v1", "state": fields.get("wpa_state", "UNKNOWN"),
                          "ssid": decode_ssid(fields.get("ssid", "")),
                          "has_ip_address": bool(fields.get("ip_address")),
                          "security": ["open", "wpa2_personal"]}
            elif method == "GET" and path == "/v1/wifi/networks":
                result = {"schema": "openaps.wifi.networks.v1", "networks": self.networks()}
            elif method == "POST" and path == "/v1/wifi/scan" and body == {}:
                now = self.clock()
                if self.last_scan is None or now - self.last_scan >= 10:
                    self.control.command("SCAN")
                    self.last_scan = now
                result = {"scan_started": True}
            elif method == "POST" and path == "/v1/wifi/networks":
                result = self.add(validate_network(body), authorize)
            else:
                raise WiFiError("not_found", 404)
            authorize()
            return 200, result

    def networks(self):
        found = {}
        for line in self.control.command("SCAN_RESULTS").splitlines()[1:]:
            fields = line.split("\t", 4)
            if len(fields) != 5:
                continue
            _, _, signal, flags, encoded = fields
            ssid = decode_ssid(encoded)
            if not ssid:
                continue
            security = "unsupported"
            if "EAP" not in flags and "WEP" not in flags:
                if "PSK" in flags and ("WPA2" in flags or "RSN" in flags):
                    security = "wpa2_personal"
                elif not any(item in flags for item in ("WPA", "RSN", "SAE", "OWE")):
                    security = "open"
            try:
                signal = int(signal)
            except ValueError:
                continue
            key = (ssid, security)
            if key not in found or signal > found[key]["signal_dbm"]:
                found[key] = {"ssid": ssid, "security": security, "signal_dbm": signal}
        return sorted(found.values(), key=lambda item: (-item["signal_dbm"], item["ssid"]))[:64]

    def add(self, network, authorize):
        # id_str identifies app-created profiles only; never modify a preexisting
        # user profile. Create disabled first, persist before requesting a switch.
        ssid = network["ssid"].encode("utf-8")
        marker = "locald-" + hashlib.sha256(ssid).hexdigest()[:32]
        previous, enabled = [], []
        for line in self.control.command("LIST_NETWORKS").splitlines()[1:]:
            fields = line.split("\t")
            network_id = fields[0]
            if network_id.isdigit():
                if "[DISABLED]" not in line:
                    enabled.append(network_id)
                if len(fields) < 2 or decode_ssid(fields[1]) != network["ssid"]:
                    continue
                try:
                    if self.control.command("GET_NETWORK %s id_str" % network_id) == '"%s"' % marker:
                        previous.append(network_id)
                except WiFiError:
                    pass
        authorize()
        network_id = self.control.command("ADD_NETWORK")
        if not network_id.isdigit():
            raise WiFiError("supplicant_rejected")
        persisted = False
        try:
            settings = [("ssid", ssid.hex()), ("id_str", '"%s"' % marker),
                        ("scan_ssid", "1" if network["hidden"] else "0"),
                        ("key_mgmt", "WPA-PSK" if network["security"] == "wpa2_personal" else "NONE")]
            if network["security"] == "wpa2_personal":
                psk = hashlib.pbkdf2_hmac("sha1", network["password"].encode("ascii"), ssid, 4096, 32).hex()
                settings.extend([("proto", "RSN"), ("psk", psk)])
            for key, value in settings:
                authorize()
                self.control.command("SET_NETWORK %s %s %s" % (network_id, key, value))
            authorize()
            # no-connect keeps the existing connection until the profile is durable.
            self.control.command("ENABLE_NETWORK %s no-connect" % network_id)
            self.control.command("SAVE_CONFIG")
            persisted = True
            authorize()
            # Restore exactly the profiles that were enabled before selection.
            try:
                self.control.command("SELECT_NETWORK %s" % network_id)
            finally:
                for old_id in enabled:
                    self.control.command("ENABLE_NETWORK %s no-connect" % old_id)
            for old_id in previous:
                self.control.command("REMOVE_NETWORK %s" % old_id)
            self.control.command("SAVE_CONFIG")
            return {"saved": True, "connection_requested": True}
        except WiFiError:
            if persisted:
                return {"saved": True, "connection_requested": False}
            raise
        finally:
            if not persisted:
                try:
                    self.control.command("REMOVE_NETWORK %s" % network_id)
                except WiFiError:
                    pass
