#!/bin/bash

# Author: Ben West @bewest
# Maintainer: @tghoward

# Written for decocare v0.0.18. Will need updating the the decocare json format changes.

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

HISTORY=${1-glucosehistory.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}
usage "$@" <<EOT
Usage: $self <glucose-history.json>
Format medtronic glucose data into oref0 format.
EOT

cat $HISTORY | \
  json -e "this.medtronic = this._type;" | \
  json -e "this.dateString = this.date + '$(date +%z)'" | \
  json -e "this.date = new Date(this.dateString).getTime();" | \
  json -E "this.type = (this.name && this.name.indexOf('GlucoseSensorData') > -1) ? 'sgv' : 'pumpdata'" | \
  json -e "this.device = 'openaps://medtronic/pump/cgm'" \
  > $OUTPUT

