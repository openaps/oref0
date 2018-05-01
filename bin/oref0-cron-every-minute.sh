#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Do all the things oref0 does once per minute, based on config files. This
should run from cron, in the myopenaps directory. Effects include trying to
get a network connection, killing crashed processes, syncing data, setting temp
basals, giving SMBs, and everything else that oref0 does. Writes to various
different log files, should (mostly) not write to stdout.
EOT

assert_cwd_contains_ini

