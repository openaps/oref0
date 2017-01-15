#!/bin/bash

# Author: Ben West @bewest
# Maintainer: @tghoward

# Written for decocare v0.0.18. Will need updating the the decocare json format changes.
self=$(basename $0)
HISTORY=${1-glucosehistory.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}
function usage ( ) {

cat <<EOT
$self <glucose-history.json>
$self - Format medtronic glucose data into oref0 format. 
EOT
}

case "$1" in
  --help|-h|help)
    usage
    exit 0
esac

cat $HISTORY | \
  json -e "this.medtronic = this._type;" | \
  json -e "this.dateString = this.date + '$(date +%z)'" | \
  json -e "this.date = new Date(this.dateString).getTime();" | \
  json -E "this.type = (this.name && this.name.indexOf('GlucoseSensorData') > -1) ? 'sgv' : 'pumpdata'" | \
  json -e "this.device = 'openaps://medtronic/pump/cgm'" \
  > $OUTPUT

