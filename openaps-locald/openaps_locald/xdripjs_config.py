from __future__ import print_function

import json
import os
import tempfile


def _xdripjs_config_path(config):
    return config.get("xdripjs_config_path") or os.path.join(config["myopenaps_dir"], "xdripjs.json")


def _read_json_object(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    raise ValueError("xdripjs config must be a JSON object")


def _atomic_write_json(path, payload):
    dirname = os.path.dirname(path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    fd, tmp_path = tempfile.mkstemp(prefix=".openaps-locald-", suffix=".json", dir=dirname or None)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, sort_keys=True, indent=2)
            f.write("\n")
        os.rename(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def read_xdripjs_config_state(config):
    path = _xdripjs_config_path(config)
    exists = os.path.exists(path)
    try:
        data = _read_json_object(path)
    except Exception as exc:
        return {
            "xdripjs_config_path": path,
            "xdripjs_config_exists": exists,
            "xdripjs_transmitter_id": None,
            "xdripjs_config_error": str(exc),
        }
    return {
        "xdripjs_config_path": path,
        "xdripjs_config_exists": exists,
        "xdripjs_transmitter_id": data.get("transmitter_id"),
    }


def update_xdripjs_transmitter_id(config, transmitter_id):
    return update_xdripjs_settings(config, transmitter_id=transmitter_id)


def update_xdripjs_settings(config, transmitter_id=None, alternate_bluetooth_channel=None):
    path = _xdripjs_config_path(config)
    data = _read_json_object(path)
    if transmitter_id is not None:
        data["transmitter_id"] = transmitter_id
    if alternate_bluetooth_channel is not None:
        data["alternate_bluetooth_channel"] = alternate_bluetooth_channel
    _atomic_write_json(path, data)
    return {
        "xdripjs_config_path": path,
        "xdripjs_transmitter_id": data.get("transmitter_id"),
        "xdripjs_alternate_bluetooth_channel": data.get("alternate_bluetooth_channel"),
    }
