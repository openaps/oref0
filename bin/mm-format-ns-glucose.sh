#!/bin/bash

# Author: Ben West @bewest
# Maintainer: Chris Oattes @cjo20

# Written for decocare v0.0.17. Will need updating the the decocare json format changes.

NSONLY=""
test "$1" = "--oref0" && NSONLY="this.glucose = this.sgv" && shift

HISTORY=${1-glucosehistory.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}


cat $HISTORY | \
  json -e "this.medtronic = this._type;" | \
  json -e "this.dateString = this.dateString ? this.dateString : (this.date + '$(date +%z)')" | \
  json -e "this.date = new Date(this.dateString).getTime();" | \
  json -e "this.type = (this.name == 'GlucoseSensorData') ? 'sgv' : 'pumpdata'" | \
  json -e "this.device = 'openaps://medtronic/pump/cgm'" | (
    json -e "$NSONLY"
  ) > $OUTPUT

