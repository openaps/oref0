#!/usr/bin/env bash

# Author: Ben West

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

HISTORY=${1-monitor/pump-history-zoned.json}
MODEL=${2-model.json}
OUTPUT=${3-/dev/fd/1}
#TZ=${3-$(date +%z)}

usage "$@" <<EOT
Usage: $self <pump-history-zoned.json> <model.json>
Format medtronic history data into Nightscout treatments data.
EOT


# | json -e "this.type = 'mm://openaps/$self'" \
model=$(json -f $MODEL)

oref0-normalize-temps $HISTORY  \
  | jq  '[ .[]
    | .medtronic = if ._type then "mm://openaps/'$self'/" + ._type else "mm://openaps/mm-format-ns-treatments/" + .eventType end 
    | .created_at = if .created_at then .created_at else .timestamp end
    | .enteredBy = "openaps://medtronic/'$model'"
    | if .glucose > 0 then .glucoseType = "openaps://medtronic/'$model'" else .enteredBy = "openaps://medtronic/'$model'" end
    | .eventType = if .eventType then .eventType else "Note" end
    | if .eventType == "Note" then .notes = ._type + " '$model' " + if .notes then .notes else "" end else .enteredBy = "openaps://medtronic/'$model'" end
    | if ._type == "AlarmSensor" and .alarm_description then .notes = .alarm_description else .enteredBy = "openaps://medtronic/'$model'" end
    ]' > $OUTPUT

