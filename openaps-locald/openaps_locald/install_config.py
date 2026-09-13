from __future__ import print_function

import os


INSTALL_DEFAULTS = {
    "materialize_temp_targets": True,
    "materialize_carbs": True,
    "merge_local_carbs_into_monitor": True,
    "materialize_bg_readings": True,
    "merge_local_bg_into_monitor": True,
    "ble_enabled": True,
    "ble_adapter": "hci0",
    "ble_name": "openaps-locald",
    "ble_http_base_url": "http://127.0.0.1:8787",
    "ble_advertised_http_base_url": None,
    "ble_service_uuid": "d8b4b1e4-6f95-4d71-9f8d-4d4e4f1d0001",
    "ble_envelope_version": 1,
    "ble_require_auth": False,
    "ble_auth_token": None,
    "ble_legacy_advertising": False,
    "xdripjs_enabled": False,
    "advertise_enabled": True,
    "advertise_adapter": "hci0",
    "advertise_interval_ms": 100,
    "advertise_connectable": True,
    "advertise_primary_name": False,
    "advertise_manage_visibility": False,
    "monitor_pumphistory_24h_zoned_path": None,
    "monitor_pumphistory_merged_path": None,
    "monitor_pumphistory_zoned_path": None,
    "monitor_pumphistory_path": None,
    "authorization_recovery_enabled": False,
    "authorization_secure_mode_enabled": False,
}


def build_install_config(existing_config, myopenaps_dir, bind_host, port, auth_token=None,
                         enable_authorization_providers=False):
    config = dict(existing_config or {})
    # Do not persist null placeholders that would obscure the legacy ns.ini
    # credential pair used at runtime.  Deliberately configured nonempty hosts
    # remain untouched and retain their no-token semantics.
    if not config.get("nightscout_host"):
        config.pop("nightscout_host", None)
        config.pop("nightscout_access_token", None)
        config.pop("nightscout_api_secret", None)
        config.pop("nightscout_credential_kind", None)
    else:
        # Authorization credentials are discovered from the existing ns.ini
        # at runtime and must never be copied into locald's JSON config.
        config.pop("nightscout_access_token", None)
        config.pop("nightscout_api_secret", None)
        config.pop("nightscout_credential_kind", None)
    settings_dir = os.path.join(myopenaps_dir, "settings")
    config["myopenaps_dir"] = myopenaps_dir
    config["bind_host"] = bind_host
    config["port"] = int(port)
    config["db_path"] = os.path.join(myopenaps_dir, "openaps-locald.sqlite3")
    config.setdefault("local_temptargets_path", os.path.join(settings_dir, "local-temptargets.json"))
    config.setdefault("local_temptarget_cancels_path", os.path.join(settings_dir, "local-temptarget-cancels.json"))
    config.setdefault("local_carbhistory_path", os.path.join(myopenaps_dir, "monitor", "local-carbhistory.json"))
    config.setdefault("monitor_carbhistory_path", os.path.join(myopenaps_dir, "monitor", "carbhistory.json"))
    config.setdefault("local_glucose_path", os.path.join(myopenaps_dir, "monitor", "local-glucose.json"))
    config.setdefault("monitor_glucose_path", os.path.join(myopenaps_dir, "monitor", "glucose.json"))
    config.setdefault("xdripjs_config_path", os.path.join(myopenaps_dir, "xdripjs.json"))
    config.setdefault("xdripjs_source_path", os.path.join(myopenaps_dir, "monitor", "xdripjs", "entry.json"))
    for key, value in INSTALL_DEFAULTS.items():
        config.setdefault(key, value)
    if enable_authorization_providers:
        # Additive rollout only: make authenticated transports available while
        # preserving legacy HTTP/BLE and leaving enforcement explicitly off.
        config["authorization_admission_enabled"] = True
        config["authorization_tls_enabled"] = True
        config["authorization_recovery_enabled"] = True
        config["ble_authorization_tls_relay_enabled"] = True
        config["authorization_secure_mode_enabled"] = False
        config["ble_require_auth"] = False
    # Older field configurations included these keys with null values.  Treat
    # null exactly like an absent authorization setting so an upgrade enters
    # the additive shadow mode rather than silently falling back to legacy.
    authorization_dir = os.path.join(myopenaps_dir, ".openaps-locald-authorization")
    if not config.get("authorization_mode"):
        config["authorization_mode"] = "shadow"
    if not config.get("authorization_identity_dir"):
        config["authorization_identity_dir"] = authorization_dir
    if not config.get("authorization_state_path"):
        config["authorization_state_path"] = os.path.join(authorization_dir, "shadow-state.json")
    if not config.get("authorization_admission_dir"):
        config["authorization_admission_dir"] = os.path.join(authorization_dir, "admission")
    if not config.get("authorization_secure_mode_dir"):
        config["authorization_secure_mode_dir"] = os.path.join(authorization_dir, "secure-mode")
    if not config.get("authorization_openssl_path"):
        config["authorization_openssl_path"] = "/usr/bin/openssl"
    if auth_token:
        config["auth_token"] = auth_token
    return config
