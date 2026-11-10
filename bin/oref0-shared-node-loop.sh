#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

# Shared node loop.
main() {
    echo
    echo Starting Shared-Node-loop at $(date):
    while true; do

        node ../src/oref0/bin/oref0-shared-node.js
        echo Tough luck, shared node crashed. Starting it againg at  $(date)
    done
}

usage "$@" <<EOT
Usage: $self
Sync data with Nightscout. Typically runs from crontab.
EOT

main "$@"
