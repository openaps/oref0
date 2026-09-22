#!/usr/bin/env bash

set -euo pipefail

LOGGER_DIR="${1:-${OPENAPS_LOGGER_DIR:-/root/src/Logger}}"
BLUETOOTH_HCI_SOCKET_VERSION="${BLUETOOTH_HCI_SOCKET_VERSION:-0.5.3-12}"
BLUETOOTH_HCI_SOCKET_TARBALL_URL="${BLUETOOTH_HCI_SOCKET_TARBALL_URL:-https://registry.npmjs.org/@abandonware/bluetooth-hci-socket/-/bluetooth-hci-socket-${BLUETOOTH_HCI_SOCKET_VERSION}.tgz}"

log() {
  printf '%s\n' "$*" >&2
}

patch_debug_shim() {
  local debug_node="${LOGGER_DIR}/node_modules/debug/src/node.js"
  if [ ! -f "${debug_node}" ]; then
    log "Logger debug module not found at ${debug_node}; skipping shim"
    return 0
  fi
  if grep -q 'formatWithOptionsShim' "${debug_node}"; then
    return 0
  fi
  python3 - "${debug_node}" <<'PY'
import io
import os
import sys

path = sys.argv[1]
with io.open(path, 'r', encoding='utf-8') as f:
    text = f.read()

needle = "require('util');\n"
shim = "\nif (typeof util.formatWithOptions !== 'function') {\n  util.formatWithOptions = function formatWithOptionsShim(options) {\n    return util.format.apply(util, Array.prototype.slice.call(arguments, 1));\n  };\n}\n"

if 'formatWithOptionsShim' not in text and needle in text:
    text = text.replace(needle, needle + shim, 1)
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(text)
PY
}

ensure_bluetooth_hci_socket() {
  local package_dir="${LOGGER_DIR}/node_modules/@abandonware/bluetooth-hci-socket"
  if (cd "${LOGGER_DIR}" && node -e "require('@abandonware/bluetooth-hci-socket')") >/dev/null 2>&1; then
    log "Logger dependency already resolves: @abandonware/bluetooth-hci-socket"
    return 0
  fi

  if [ ! -d "${LOGGER_DIR}/node_modules" ]; then
    log "Logger node_modules missing at ${LOGGER_DIR}/node_modules"
    return 1
  fi

  local node_pre_gyp="${LOGGER_DIR}/node_modules/.bin/node-pre-gyp"
  if [ ! -x "${node_pre_gyp}" ]; then
    log "Logger node-pre-gyp not found at ${node_pre_gyp}"
    return 1
  fi

  local tmpdir pkg_src
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' EXIT

  log "Installing @abandonware/bluetooth-hci-socket ${BLUETOOTH_HCI_SOCKET_VERSION} into ${LOGGER_DIR}"
  curl -fsSL "${BLUETOOTH_HCI_SOCKET_TARBALL_URL}" -o "${tmpdir}/bluetooth-hci-socket.tgz"
  tar -xzf "${tmpdir}/bluetooth-hci-socket.tgz" -C "${tmpdir}"
  pkg_src="$(find "${tmpdir}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [ -z "${pkg_src}" ]; then
    log "Could not unpack bluetooth-hci-socket tarball"
    return 1
  fi

  (
    cd "${pkg_src}"
    "${node_pre_gyp}" install --build-from-source
  )

  rm -rf "${package_dir}"
  mkdir -p "$(dirname "${package_dir}")"
  cp -a "${pkg_src}" "${package_dir}"
  log "Installed bluetooth-hci-socket into ${package_dir}"
}

if [ ! -d "${LOGGER_DIR}" ]; then
  log "Logger directory not found at ${LOGGER_DIR}; skipping xDripJS bootstrap"
  exit 0
fi

ensure_bluetooth_hci_socket
patch_debug_shim

if (cd "${LOGGER_DIR}" && node -e "require('@abandonware/bluetooth-hci-socket'); process.exit(0)") >/dev/null 2>&1; then
  log "Logger xDripJS runtime bootstrap complete for ${LOGGER_DIR}"
else
  log "Logger xDripJS runtime bootstrap did not fully verify for ${LOGGER_DIR}"
  exit 1
fi
