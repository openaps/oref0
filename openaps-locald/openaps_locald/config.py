from __future__ import print_function

import argparse
import configparser
import hashlib
import json
import os
import re
import shlex
import socket
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse


DEFAULT_CONFIG_BASENAME = "openaps-locald.json"
DEFAULT_BLE_SERVICE_UUID = "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0001"
NIGHTSCOUT_ACCESS_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_]+-[A-Za-z0-9]{16}$")


def _read_json(path):
    with open(path, "r") as f:
        return json.load(f)


def _legacy_patient_id_from_nightscout(host):
    if not host:
        return "local-default"
    normalized = host.strip().lower().rstrip("/")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return "ns_" + digest


def _ios_patient_id_from_nightscout(host):
    if not host:
        return "local-default"
    value = host.strip()
    parsed = urlparse(value if "://" in value else "//" + value)
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return "local-default"
    identity = "nightscout://" + hostname
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None:
        identity += ":%d" % port
    digest = 0xcbf29ce484222325
    for byte in identity.encode("utf-8"):
        if not isinstance(byte, int):
            byte = ord(byte)
        digest ^= byte
        digest = (digest * 0x100000001b3) & 0xffffffffffffffff
    return "ns_%016x" % digest


def _patient_id_from_nightscout(host):
    # Preserve the deployed primary identity. Existing phones and stored events
    # may already use it; the iOS-canonical equivalent is accepted as an alias.
    return _legacy_patient_id_from_nightscout(host)


def accepted_patient_ids(config):
    current = config.get("patient_id") or "local-default"
    host = config.get("nightscout_host")
    legacy = _legacy_patient_id_from_nightscout(host)
    ios = _ios_patient_id_from_nightscout(host)
    if current in (legacy, ios):
        return set([legacy, ios])
    return set([current])


def load_preferences(myopenaps_dir):
    path = os.path.join(myopenaps_dir, "preferences.json")
    if not os.path.exists(path):
        return {}
    return _read_json(path)


def load_nightscout_credentials(myopenaps_dir):
    """Read the credential oref0 already uses without copying it into locald JSON."""
    path = os.path.join(myopenaps_dir, "ns.ini")
    if not os.path.exists(path):
        return {}
    parser = configparser.ConfigParser()
    try:
        with open(path, "r") as handle:
            if hasattr(parser, "read_file"):
                parser.read_file(handle)
            else:
                parser.readfp(handle)
        section = 'device "ns"'
        if not parser.has_section(section) or not parser.has_option(section, "args"):
            return {}
        arguments = shlex.split(parser.get(section, "args"))
    except (IOError, ValueError, configparser.Error):
        return {}
    if len(arguments) < 3 or arguments[0] != "ns":
        return {}
    host = arguments[1].strip()
    credential = arguments[2].strip()
    credential_had_token_prefix = credential.startswith("token=")
    if credential.startswith("token="):
        credential = credential[len("token="):]
    if not credential:
        return {"nightscout_host": host}
    # A legacy API secret is also the third ns.ini argument, but it cannot be
    # exchanged for an API-v3 JWT and has no server-authenticated subject.
    # Distinguish it from a token instead of repeatedly sending it to the JWT
    # endpoint. Accept a bare token only when it has Nightscout's access-token
    # shape; older setup scripts normally retain the explicit token= prefix.
    if not credential_had_token_prefix and not NIGHTSCOUT_ACCESS_TOKEN_PATTERN.match(credential):
        return {
            "nightscout_host": host,
            "nightscout_credential_kind": "legacy_api_secret",
            # Keep the deployed secret in memory only. The installer strips
            # credential fields from openaps-locald.json.
            "nightscout_api_secret": credential,
        }
    return {
        "nightscout_host": host,
        "nightscout_access_token": credential,
        "nightscout_credential_kind": "access_token",
    }


def default_config(myopenaps_dir):
    prefs = load_preferences(myopenaps_dir)
    nightscout_credentials = load_nightscout_credentials(myopenaps_dir)
    # Keep the host and token from ns.ini as one credential pair. Falling back
    # to a preferences host while using the ns.ini token could enroll into the
    # wrong Nightscout origin after a migration.
    nightscout_host = nightscout_credentials.get("nightscout_host") or prefs.get("nightscout_host")
    settings_dir = os.path.join(myopenaps_dir, "settings")
    authorization_dir = os.path.join(myopenaps_dir, ".openaps-locald-authorization")
    return {
        "rig_id": socket.gethostname(),
        "patient_id": _patient_id_from_nightscout(nightscout_host),
        "myopenaps_dir": myopenaps_dir,
        "db_path": os.path.join(myopenaps_dir, "openaps-locald.sqlite3"),
        "local_temptargets_path": os.path.join(settings_dir, "local-temptargets.json"),
        "local_temptarget_cancels_path": os.path.join(settings_dir, "local-temptarget-cancels.json"),
        "local_carbhistory_path": os.path.join(myopenaps_dir, "monitor", "local-carbhistory.json"),
        "monitor_carbhistory_path": os.path.join(myopenaps_dir, "monitor", "carbhistory.json"),
        "local_glucose_path": os.path.join(myopenaps_dir, "monitor", "local-glucose.json"),
        "monitor_glucose_path": os.path.join(myopenaps_dir, "monitor", "glucose.json"),
        "monitor_pumphistory_24h_zoned_path": os.path.join(myopenaps_dir, "monitor", "pumphistory-24h-zoned.json"),
        "monitor_pumphistory_merged_path": os.path.join(myopenaps_dir, "monitor", "pumphistory-merged.json"),
        "monitor_pumphistory_zoned_path": os.path.join(myopenaps_dir, "monitor", "pumphistory-zoned.json"),
        "monitor_pumphistory_path": os.path.join(myopenaps_dir, "monitor", "pumphistory.json"),
        "xdripjs_config_path": os.path.join(myopenaps_dir, "xdripjs.json"),
        "xdripjs_source_path": os.path.join(myopenaps_dir, "monitor", "xdripjs", "entry.json"),
        "bind_host": "0.0.0.0",
        "port": 8787,
        "auth_token": None,
        "materialize_temp_targets": False,
        "materialize_carbs": False,
        "merge_local_carbs_into_monitor": False,
        "materialize_bg_readings": False,
        "merge_local_bg_into_monitor": False,
        "ble_enabled": False,
        "ble_adapter": "hci0",
        "ble_name": "openaps-locald",
        "ble_http_base_url": "http://127.0.0.1:8787",
        "ble_advertised_http_base_url": None,
        "ble_service_uuid": DEFAULT_BLE_SERVICE_UUID,
        "ble_envelope_version": 1,
        "ble_require_auth": False,
        "ble_auth_token": None,
        "ble_authorization_tls_relay_enabled": False,
        "ble_legacy_advertising": False,
        "xdripjs_enabled": False,
        "advertise_enabled": True,
        "advertise_adapter": "hci0",
        "advertise_interval_ms": 100,
        "advertise_connectable": True,
        "advertise_primary_name": False,
        "advertise_manage_visibility": False,
        "nightscout_host": nightscout_host,
        "nightscout_access_token": nightscout_credentials.get("nightscout_access_token"),
        "nightscout_api_secret": nightscout_credentials.get("nightscout_api_secret"),
        "nightscout_credential_kind": nightscout_credentials.get("nightscout_credential_kind"),
        "authorization_mode": "shadow",
        "authorization_identity_dir": authorization_dir,
        "authorization_state_path": os.path.join(authorization_dir, "shadow-state.json"),
        "authorization_admission_dir": os.path.join(authorization_dir, "admission"),
        "authorization_secure_mode_dir": os.path.join(authorization_dir, "secure-mode"),
        "authorization_recovery_enabled": False,
        "authorization_secure_mode_enabled": False,
        "authorization_openssl_path": "/usr/bin/openssl",
    }


def load_config(config_path=None, myopenaps_dir=None):
    if myopenaps_dir is None:
        myopenaps_dir = os.environ.get("OPENAPS_DIR") or os.getcwd()
    config = default_config(myopenaps_dir)

    loaded = {}
    if config_path is None:
        candidate = os.path.join(myopenaps_dir, DEFAULT_CONFIG_BASENAME)
        config_path = candidate if os.path.exists(candidate) else None

    if config_path:
        loaded = _read_json(config_path)
        if "myopenaps_dir" in loaded and loaded["myopenaps_dir"] != myopenaps_dir:
            config = default_config(loaded["myopenaps_dir"])
    # A prior installer emitted null Nightscout placeholders.  They must not
    # mask the existing ns.ini credential pair on the next daemon launch.  An
    # explicit nonempty host remains authoritative and is never paired with a
    # token from a different source.
    if not loaded.get("nightscout_host"):
        loaded.pop("nightscout_host", None)
        loaded.pop("nightscout_access_token", None)
    elif "nightscout_access_token" not in loaded:
        loaded["nightscout_access_token"] = None
    config.update(loaded)

    config["port"] = int(config.get("port") or 8787)
    if not config.get("db_path"):
        config["db_path"] = os.path.join(config["myopenaps_dir"], "openaps-locald.sqlite3")
    if not config.get("ble_service_uuid"):
        config["ble_service_uuid"] = DEFAULT_BLE_SERVICE_UUID
    return config


def build_arg_parser():
    parser = argparse.ArgumentParser(description="OpenAPS local event sync daemon")
    parser.add_argument("--config", help="Path to openaps-locald JSON config")
    parser.add_argument("--myopenaps-dir", default=None, help="OpenAPS loop directory")
    parser.add_argument("--host", default=None, help="HTTP bind host")
    parser.add_argument("--port", type=int, default=None, help="HTTP bind port")
    parser.add_argument("--db", default=None, help="SQLite database path")
    parser.add_argument("--once", action="store_true", help="Initialize database and print status, then exit")
    return parser


def config_from_args(args):
    config = load_config(args.config, args.myopenaps_dir)
    if args.host is not None:
        config["bind_host"] = args.host
    if args.port is not None:
        config["port"] = args.port
    if args.db is not None:
        config["db_path"] = args.db
    return config
