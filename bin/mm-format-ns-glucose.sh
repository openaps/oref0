#!/bin/bash

# Author: Ben West @bewest
# Maintainer: Chris Oattes @cjo20

# Written for decocare v0.0.17. Will need updating the the decocare json format changes.

NSONLY=""
test "$1" = "--oref0" && NSONLY="this.glucose = this.sgv" && shift

self=$(basename $0)
function usage ( ) {

cat <<EOT
$self [--oref0] <medtronic-glucose.json>
$self - Format Medtronic glucose data into something acceptable to Nightscout.
EOT
}

case "$1" in
  --help|-h|help)
    usage
    exit 0
esac

HISTORY=${1-glucosehistory.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}


cat $HISTORY | \
  json -E "this.medtronic = this._type;" | \
  json -E "this.dateString = this.dateString ? this.dateString : (this.date + '$(date +%z)')" | \
  json -E "this.date = new Date(this.dateString).getTime();" | \
  json -E "this.type = (this.name && this.name.indexOf('GlucoseSensorData') > -1) ? 'sgv' : 'pumpdata'" | \
  json -E "this.device = 'openaps://medtronic/pump/cgm'" | (
    json -E "$NSONLY"
  ) > $OUTPUT

