#!/usr/bin/env bash

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
  jq '[ .[]
    | .medtronic = ._type
    | if ( ( .dateString | not ) and ( .date | tostring | test(":") ) ) then
      .dateString = ( [ .date, "'$(date +%z)'" ] | join("") ) else . end
    | if ( ( .dateString | not ) and ( .date | test(".") | not ) ) then .dateString = ( .date | todate ) else . end
    | if .date | tostring | test(":") then .date = ( .dateString | strptime("%Y-%m-%dT%H:%M:%S%z") | mktime * 1000 ) else . end
    | .type = if .name and (.name | test("GlucoseSensorData")) then "sgv" else "pumpdata" end
    | .device = "openaps://medtronic/pump/cgm" ]' \
   > $OUTPUT

