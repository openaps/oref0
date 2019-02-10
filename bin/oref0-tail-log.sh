#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self
Monitors /var/log/openaps/pump-loop.log
EOF


tail -n 100 -F /var/log/openaps/pump-loop.log
