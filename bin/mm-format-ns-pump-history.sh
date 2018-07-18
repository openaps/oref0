#!/bin/bash

# Author: Ben West
# Maintainer: Scott Leibrand

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self <medtronic-pump-history.json>
Format Medtronic pump-history data into something acceptable to Nightscout.
EOT


HISTORY=${1-pumphistory.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}

cat $HISTORY | \
  json -e "this.medtronic = this._type;"  \
    -e "this.dateString = this.timestamp + '$(date +%z)'"  \
    -e "this.type = 'medtronic'"  \
    -e "this.date = this.date ? this.date : new Date(Date.parse(this.dateString)).getTime( )" \
  > $OUTPUT


