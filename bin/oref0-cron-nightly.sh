#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Do all the things that oref0 does once per night, based on config files.
Currently this just means autotune. This should run from cron, in the
myopenaps directory. By default, this happens at 4:05am every night.
EOT

assert_cwd_contains_ini

