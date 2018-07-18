#!/bin/bash

# Author: Ben West @bewest
# Maintainer: Chris Oattes @cjo20

# Written for decocare v0.0.17. Will need updating the the decocare json format changes.

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self [--oref0] <medtronic-glucose.json>
Format Medtronic glucose data into something acceptable to Nightscout.
EOT

NSONLY=""
test "$1" = "--oref0" && NSONLY="this.glucose = this.sgv" && shift

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

