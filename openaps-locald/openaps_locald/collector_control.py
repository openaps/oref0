from __future__ import print_function

import errno
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time

from .xdripjs import _coerce_int, read_latest_xdripjs_record


COLLECTOR = "xdripjs"
LOGGER_PATH = "/usr/local/bin/Logger"
LOGGER_REAL_PATH = "/root/src/Logger/xdrip-get-entries.sh"
LOGGER_WORKDIR = "/root/src/Logger"
LOGGER_LOG_PATH = "/var/log/openaps/logger-loop.log"
LEGACY_MANAGED_CRON_LINE = "* * * * * cd /root/src/Logger && ps aux | grep -v grep | grep -q Logger || /usr/local/bin/Logger >> /var/log/openaps/logger-loop.log 2>&1"
MANAGED_CRON_LINE = "* * * * * cd /root/src/Logger && ps -eo state=,args= | grep -v grep | grep -v \"^[[:space:]]*Z\" | grep -q Logger || /usr/local/bin/Logger >> /var/log/openaps/logger-loop.log 2>&1"
COMMENTED_MANAGED_CRON_LINE = "#" + MANAGED_CRON_LINE
MANAGED_CRON_LINES = (LEGACY_MANAGED_CRON_LINE, MANAGED_CRON_LINE)
LOGGER_CRON_RE = re.compile(
    r"^\* \* \* \* \* cd /root/src/Logger && ps .+ \|\| "
    r"/usr/local/bin/Logger >> /var/log/openaps/logger-loop\.log 2>&1$"
)
STOP_TERM_SECONDS = 5.0
STOP_KILL_SECONDS = 2.0


def _config_path(config):
    return config.get("xdripjs_config_path") or os.path.join(config["myopenaps_dir"], "xdripjs.json")


def _read_json_object(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("xdripjs config must be a JSON object")
    return data


def _atomic_replace(path, content, mode=None):
    directory = os.path.dirname(path) or "."
    if not os.path.exists(directory):
        os.makedirs(directory)
    fd, tmp_path = tempfile.mkstemp(prefix=".openaps-locald-", dir=directory)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.rename(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _atomic_write_json(path, payload):
    mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else 0o600
    backup_path = path + ".pre-phone-election"
    if os.path.exists(path) and not os.path.exists(backup_path):
        shutil.copy2(path, backup_path)
    _atomic_replace(path, json.dumps(payload, sort_keys=True, indent=2) + "\n", mode=mode)


def _read_crontab():
    try:
        content = subprocess.check_output(["crontab", "-l"], stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError):
        return []
    if not isinstance(content, str):
        content = content.decode("utf-8")
    return content.splitlines()


def _is_managed_logger_cron_line(line):
    stripped = line.strip()
    if stripped.startswith("#"):
        stripped = stripped[1:].strip()
    return stripped in MANAGED_CRON_LINES or bool(LOGGER_CRON_RE.match(stripped))


def _cron_enabled(config):
    return any(
        not line.lstrip().startswith("#") and _is_managed_logger_cron_line(line)
        for line in _read_crontab()
    )


def _install_crontab(lines):
    content = "\n".join(lines)
    if lines:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".openaps-locald-cron-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        subprocess.check_call(["crontab", tmp_path])
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _set_cron_enabled(config, enabled):
    lines = _read_crontab()
    updated = [line for line in lines if not _is_managed_logger_cron_line(line)]
    updated.append(MANAGED_CRON_LINE if enabled else COMMENTED_MANAGED_CRON_LINE)
    if updated == lines:
        return False
    _install_crontab(updated)
    return True


def _read_process_state(pid):
    with open("/proc/%d/status" % pid, "r") as f:
        for line in f:
            if line.startswith("State:"):
                fields = line.split()
                return fields[1] if len(fields) > 1 else ""
    return ""


def _read_process_argv(pid):
    with open("/proc/%d/cmdline" % pid, "rb") as f:
        raw = f.read()
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def _is_logger_argv(argv):
    if not argv:
        return False
    executable = argv[0]
    if executable in (LOGGER_PATH, LOGGER_REAL_PATH):
        return True
    executable_name = os.path.basename(executable)
    if executable_name in ("bash", "sh") and len(argv) > 1:
        return argv[1] in (LOGGER_PATH, LOGGER_REAL_PATH)
    if executable_name == "node":
        return any("xdrip" in argument.lower() for argument in argv[1:])
    return False


def _logger_pids():
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    pids = []
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            pid = int(entry)
            if _read_process_state(pid).startswith("Z"):
                continue
            if _is_logger_argv(_read_process_argv(pid)):
                pids.append(pid)
        except (OSError, ValueError):
            continue
    return pids


def _process_count():
    return len(_logger_pids())


def _start_logger():
    log_directory = os.path.dirname(LOGGER_LOG_PATH)
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)
    devnull = open(os.devnull, "rb")
    log = open(LOGGER_LOG_PATH, "ab")
    try:
        return subprocess.Popen(
            [LOGGER_PATH],
            cwd=LOGGER_WORKDIR,
            stdin=devnull,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=True,
        )
    finally:
        devnull.close()
        log.close()


def _wait_for_no_loggers(timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _logger_pids():
            return True
        time.sleep(0.2)
    return not _logger_pids()


def _stop_loggers():
    pids = _logger_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            if exc.errno != errno.ESRCH:
                raise
    if _wait_for_no_loggers(STOP_TERM_SECONDS):
        return
    for pid in _logger_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as exc:
            if exc.errno != errno.ESRCH:
                raise
    if not _wait_for_no_loggers(STOP_KILL_SECONDS):
        raise RuntimeError("Logger did not stop after TERM/KILL")


def _state(config, payload):
    path = _config_path(config)
    try:
        data = _read_json_object(path)
        transmitter_id = data.get("transmitter_id")
        alternate = data.get("alternate_bluetooth_channel")
        config_error = None
    except Exception as exc:
        transmitter_id = None
        alternate = None
        config_error = str(exc)
    process_count = _process_count()
    latest_direct = read_latest_xdripjs_record(config)
    if latest_direct is not None:
        record = latest_direct["record"]
        glucose = _coerce_int(record.get("sgv"))
        if glucose is None:
            glucose = _coerce_int(record.get("glucose"))
        if glucose is None or glucose <= 0:
            latest_direct = None
    direct_millis = latest_direct["date_millis"] if latest_direct else None
    direct_age = int(time.time() - direct_millis / 1000.0) if direct_millis is not None else None
    if process_count == 0:
        health = "stopped"
    elif direct_age is None:
        health = "no_direct_reading"
    elif direct_age < -300:
        health = "reading_clock_skew"
    elif direct_age > 900:
        health = "stale_direct_reading"
    else:
        health = "fresh_direct_reading"
    result = {
        "desired_state": payload.get("desired_state"),
        "actual_state": "running" if process_count > 0 else "stopped",
        "transmitter_id": transmitter_id,
        "alternate_bluetooth_channel": alternate,
        "election_id": payload.get("election_id"),
        "cron_enabled": _cron_enabled(config),
        "process_count": process_count,
        "collector_health": health,
        "last_direct_bg_millis": direct_millis,
        "direct_bg_age_seconds": direct_age,
    }
    if config_error:
        result["config_error"] = config_error
    return result


def read_collector_status(config, payload=None):
    return _state(config, payload or {})


def _configure(config, payload):
    path = _config_path(config)
    data = _read_json_object(path)
    changed = (
        data.get("transmitter_id") != payload["transmitter_id"]
        or data.get("alternate_bluetooth_channel") != payload["alternate_bluetooth_channel"]
    )
    if not changed:
        return False
    data["transmitter_id"] = payload["transmitter_id"]
    data["alternate_bluetooth_channel"] = payload["alternate_bluetooth_channel"]
    _atomic_write_json(path, data)
    return True


def apply_collector_control(config, payload):
    desired_state = payload["desired_state"]
    if desired_state == "status":
        details = read_collector_status(config, payload)
    else:
        if desired_state == "running":
            changed = _configure(config, payload)
            _set_cron_enabled(config, False)
            process_count = _process_count()
            if changed or process_count > 1:
                _stop_loggers()
            if _process_count() == 0:
                _start_logger()
                time.sleep(0.2)
            _set_cron_enabled(config, True)
        elif desired_state == "stopped":
            _set_cron_enabled(config, False)
            _stop_loggers()
        details = read_collector_status(config, payload)
    details["materialization"] = "collector_control_%s" % desired_state
    return details
