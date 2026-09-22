#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MYOPENAPS_DIR="${1:-/root/myopenaps}"
HOST="${2:-0.0.0.0}"
PORT="${3:-8787}"
AUTH_TOKEN="${4:-}"
LOGGER_DIR="${OPENAPS_LOGGER_DIR:-/root/src/Logger}"
ENABLE_AUTHORIZATION_PROVIDERS="${OPENAPS_LOCALD_ENABLE_AUTHORIZATION_PROVIDERS:-false}"
ALLOW_INSECURE_HTTP_PROOF="${OPENAPS_LOCALD_ALLOW_INSECURE_HTTP_PROOF:-false}"

CONFIG_FILE="${MYOPENAPS_DIR}/openaps-locald.json"
UNIT_FILE="/etc/systemd/system/openaps-locald.service"
PACKAGE_DIR="/usr/local/src/oref0/openaps-locald"

mkdir -p "${MYOPENAPS_DIR}"

PYTHONPATH="${ROOT_DIR}/openaps-locald" CONFIG_FILE="${CONFIG_FILE}" MYOPENAPS_DIR="${MYOPENAPS_DIR}" HOST_BIND="${HOST}" PORT_BIND="${PORT}" AUTH_TOKEN="${AUTH_TOKEN}" ENABLE_AUTHORIZATION_PROVIDERS="${ENABLE_AUTHORIZATION_PROVIDERS}" ALLOW_INSECURE_HTTP_PROOF="${ALLOW_INSECURE_HTTP_PROOF}" python3 - <<'PY'
import json, os
from openaps_locald.install_config import build_install_config

path = os.environ["CONFIG_FILE"]
myopenaps_dir = os.environ["MYOPENAPS_DIR"]
host = os.environ["HOST_BIND"]
port = int(os.environ["PORT_BIND"])
auth_token = os.environ.get("AUTH_TOKEN", "")
enable_authorization_providers = os.environ.get(
    "ENABLE_AUTHORIZATION_PROVIDERS", "false"
).lower() == "true"
allow_insecure_http_proof = os.environ.get(
    "ALLOW_INSECURE_HTTP_PROOF", "false"
).lower() == "true"
config = {}
if os.path.exists(path):
    with open(path) as f:
        try:
            config = json.load(f)
        except Exception:
            config = {}
config = build_install_config(
    config, myopenaps_dir, host, port, auth_token,
    enable_authorization_providers=enable_authorization_providers,
)
if allow_insecure_http_proof:
    config["allow_legacy_http_proof"] = True
if auth_token:
    config["auth_token"] = auth_token
admission_root = config["authorization_admission_dir"]
for directory in ((admission_root, config["authorization_secure_mode_dir"]) +
        tuple(os.path.join(admission_root, name)
        for name in ("settings-epoch", "key-epoch", "candidates", "committed", "policy-anchor"))):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_uid != os.geteuid():
            raise RuntimeError("authorization admission directory has the wrong owner")
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
with open(path + ".new", "w") as f:
    json.dump(config, f, sort_keys=True, indent=2)
    f.write("\n")
os.rename(path + ".new", path)
PY

install -m 0755 "${ROOT_DIR}/bin/openaps-locald" /usr/local/bin/openaps-locald
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-merge-carbs" /usr/local/bin/openaps-locald-merge-carbs
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-ble" /usr/local/bin/openaps-locald-ble
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-advertise" /usr/local/bin/openaps-locald-advertise
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-authorization-smoke" /usr/local/bin/openaps-locald-authorization-smoke
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-sync-xdripjs" /usr/local/bin/openaps-locald-sync-xdripjs
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-replay-cgm-config" /usr/local/bin/openaps-locald-replay-cgm-config
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-bootstrap-logger.sh" /usr/local/bin/openaps-locald-bootstrap-logger.sh
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-install-carb-hook.sh" /usr/local/bin/openaps-locald-install-carb-hook.sh
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-refresh-pump-status" /usr/local/bin/openaps-locald-refresh-pump-status
install -m 0755 "${ROOT_DIR}/bin/openaps-locald-install-pump-status-hook.sh" /usr/local/bin/openaps-locald-install-pump-status-hook.sh
mkdir -p "$(dirname "${PACKAGE_DIR}")"
rm -rf "${PACKAGE_DIR}.new"
mkdir -p "${PACKAGE_DIR}.new"
cp -a "${ROOT_DIR}/openaps-locald/." "${PACKAGE_DIR}.new/"
rm -rf "${PACKAGE_DIR}"
mv "${PACKAGE_DIR}.new" "${PACKAGE_DIR}"
install -m 0644 "${ROOT_DIR}/openaps-locald/systemd/openaps-locald.service" "${UNIT_FILE}"
install -m 0644 "${ROOT_DIR}/openaps-locald/systemd/openaps-locald-ble.service" /etc/systemd/system/openaps-locald-ble.service
install -m 0644 "${ROOT_DIR}/openaps-locald/systemd/openaps-locald-advertise.service" /etc/systemd/system/openaps-locald-advertise.service
install -m 0644 "${ROOT_DIR}/openaps-locald/systemd/openaps-locald-sync-xdripjs.service" /etc/systemd/system/openaps-locald-sync-xdripjs.service
install -m 0644 "${ROOT_DIR}/openaps-locald/systemd/openaps-locald-sync-xdripjs.timer" /etc/systemd/system/openaps-locald-sync-xdripjs.timer
install -m 0644 "${ROOT_DIR}/openaps-locald/dbus/com.openaps.locald.conf" /etc/dbus-1/system.d/com.openaps.locald.conf

systemctl daemon-reload
systemctl enable openaps-locald
systemctl restart openaps-locald
systemctl enable openaps-locald-ble
systemctl restart openaps-locald-ble
systemctl enable openaps-locald-advertise
systemctl restart openaps-locald-advertise
XDRIPJS_ENABLED="$(
  python3 - "${CONFIG_FILE}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r") as f:
    config = json.load(f)
print("true" if config.get("xdripjs_enabled") else "false")
PY
)"
MERGE_CARBS_ENABLED="$(
  python3 - "${CONFIG_FILE}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r") as f:
    config = json.load(f)
print("true" if config.get("merge_local_carbs_into_monitor") else "false")
PY
)"
MATERIALIZE_BGS_ENABLED="$(
  python3 - "${CONFIG_FILE}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r") as f:
    config = json.load(f)
print("true" if config.get("materialize_bg_readings") else "false")
PY
)"
if [ "${MERGE_CARBS_ENABLED}" = "true" ] && [ -f /root/src/oref0/bin/oref0-ns-loop.sh ]; then
  /usr/local/bin/openaps-locald-install-carb-hook.sh "${MYOPENAPS_DIR}" /root/src/oref0/bin/oref0-ns-loop.sh apply || \
    echo "Warning: failed to install carb merge hook" >&2
fi
if [ -f /root/src/oref0/bin/oref0-ns-loop.sh ]; then
  /usr/local/bin/openaps-locald-install-pump-status-hook.sh "${MYOPENAPS_DIR}" /root/src/oref0/bin/oref0-ns-loop.sh apply || \
    echo "Warning: failed to install pump status refresh hook" >&2
fi
if [ "${XDRIPJS_ENABLED}" = "true" ]; then
  systemctl enable openaps-locald-sync-xdripjs.timer
  systemctl restart openaps-locald-sync-xdripjs.timer

  if [ -x /usr/local/bin/openaps-locald-bootstrap-logger.sh ]; then
    /usr/local/bin/openaps-locald-bootstrap-logger.sh "${LOGGER_DIR}"
  fi
else
  systemctl disable --now openaps-locald-sync-xdripjs.timer >/dev/null 2>&1 || true
  if crontab -l >/tmp/openaps-locald-crontab.before 2>/dev/null; then
    set +e
    OPENAPS_LOCALD_DISABLE_OFFLINE_TT="${MATERIALIZE_BGS_ENABLED}" python3 - <<'PY'
from __future__ import print_function

import io
import os

source = "/tmp/openaps-locald-crontab.before"
target = "/tmp/openaps-locald-crontab.after"
changed = False
disable_offline_tt = os.environ.get("OPENAPS_LOCALD_DISABLE_OFFLINE_TT") == "true"
with io.open(source, "r", encoding="utf-8") as f:
    lines = f.readlines()
out = []
for line in lines:
    stripped = line.lstrip()
    if "/usr/local/bin/Logger" in line and not stripped.startswith("#"):
        out.append("# openaps-locald disabled for BLE coexistence: " + line)
        changed = True
    elif (
        disable_offline_tt
        and not stripped.startswith("#")
        and "oref0-append-local-temptarget 120 10" in line
        and "iwgetid" in line
    ):
        out.append("# openaps-locald disabled offline xdripjs temp target: " + line)
        changed = True
    else:
        out.append(line)
with io.open(target, "w", encoding="utf-8") as f:
    f.writelines(out)
raise SystemExit(0 if changed else 2)
PY
    CRON_RESULT="$?"
    set -e
    case "${CRON_RESULT}" in
      0) crontab /tmp/openaps-locald-crontab.after ;;
      2) ;;
      *) echo "Warning: failed to inspect legacy Logger crontab" >&2 ;;
    esac
  fi
fi

echo "Installed openaps-locald config at ${CONFIG_FILE}"
echo "Installed systemd unit at ${UNIT_FILE}"
echo "Bind host: ${HOST}:${PORT}"
