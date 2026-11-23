#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MYOPENAPS_DIR="${1:-/root/myopenaps}"
LOOP_PATH="${2:-/root/src/oref0/bin/oref0-ns-loop.sh}"
MODE="${3:-apply}"

HOOK_BIN="/usr/local/bin/openaps-locald-refresh-pump-status"
BACKUP_PATH="${LOOP_PATH}.openaps-locald-pump-status.bak"
MARKER="# openaps-locald: refresh pump status before device status"

SOURCE_HOOK="${ROOT_DIR}/bin/openaps-locald-refresh-pump-status"
if [ "$(readlink -f "${SOURCE_HOOK}")" != "$(readlink -f "${HOOK_BIN}")" ]; then
    install -m 0755 "${SOURCE_HOOK}" "${HOOK_BIN}"
fi

if [ "${MODE}" = "print" ]; then
    cat <<EOF
Would install pump status hook:
  hook: ${HOOK_BIN}
  loop: ${LOOP_PATH}
  backup: ${BACKUP_PATH}
  inserted marker: ${MARKER}
EOF
    exit 0
fi

if [ "${MODE}" = "remove" ]; then
    if [ -f "${BACKUP_PATH}" ]; then
        cp "${BACKUP_PATH}" "${LOOP_PATH}"
        echo "Restored ${LOOP_PATH} from ${BACKUP_PATH}"
    else
        echo "No backup found at ${BACKUP_PATH}" >&2
        exit 1
    fi
    exit 0
fi

if [ ! -f "${BACKUP_PATH}" ]; then
    cp "${LOOP_PATH}" "${BACKUP_PATH}"
fi

python3 - "${LOOP_PATH}" "${HOOK_BIN}" "${MYOPENAPS_DIR}" "${MARKER}" <<'PY'
import io
import os
import sys

loop_path, hook_bin, myopenaps_dir, marker = sys.argv[1:5]
with io.open(loop_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

if any(marker in line for line in lines):
    sys.exit(0)

insert_at = None
for idx, line in enumerate(lines):
    if line.strip() == "battery_status":
        insert_at = idx + 1
        break

if insert_at is None:
    raise SystemExit("Could not find battery_status line in %s" % loop_path)

block = [
    "    %s\n" % marker,
    "    if command -v %s >/dev/null 2>&1; then\n" % os.path.basename(hook_bin),
    "        %s --myopenaps-dir \"%s\" || true\n" % (os.path.basename(hook_bin), myopenaps_dir),
    "    fi\n",
]
lines[insert_at:insert_at] = block

with io.open(loop_path, "w", encoding="utf-8") as f:
    f.writelines(lines)
PY

echo "Installed pump status hook into ${LOOP_PATH}"
echo "Backup saved at ${BACKUP_PATH}"
echo "Use: ${HOOK_BIN} --myopenaps-dir ${MYOPENAPS_DIR}"
