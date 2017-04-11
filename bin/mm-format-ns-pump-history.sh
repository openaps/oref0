#!/bin/bash

# Author: Ben West
# Maintainer: Scott Leibrand

self=$(basename $0)
function usage ( ) {

cat <<EOT
$self <medtronic-pump-history.json>
$self - Format Medtronic pump-history data into something acceptable to Nightscout.
EOT
}

case "$1" in
  --help|-h|help)
    usage
    exit 0
esac


HISTORY=${1-pumphistory.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}

cat $HISTORY | \
  json -e "this.medtronic = this._type;"  \
    -e "this.dateString = this.timestamp + '$(date +%z)'"  \
    -e "this.type = 'medtronic'"  \
    -e "this.date = this.date ? this.date : new Date(Date.parse(this.dateString)).getTime( )" \
  > $OUTPUT


