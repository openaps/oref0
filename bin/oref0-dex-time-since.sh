#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self <glucose.json>
Given a glucose log file, output the number of minutes it's been since the
latest sample.
EOT

GLUCOSE=$1

cat $GLUCOSE | json -e "this.minAgo=Math.round(100*(new Date()-new Date(this.dateString))/60/1000)/100" | json -a minAgo | head -n 1

