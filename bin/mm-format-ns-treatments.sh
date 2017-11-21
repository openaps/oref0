#!/bin/bash

# Author: Ben West

HISTORY=${1-monitor/pump-history-zoned.json}
MODEL=${2-model.json}
OUTPUT=${3-/dev/fd/1}
#TZ=${3-$(date +%z)}
self=$(basename $0)
function usage ( ) {

cat <<EOT
$self <pump-history-zoned.json> <model.json>
$self - Format medtronic history data into Nightscout treatments data.
EOT
}

case "$1" in
  --help|-h|help)
    usage
    exit 0
esac


# | json -e "this.type = 'mm://openaps/$self'" \
model=$(json -f $MODEL)

oref0-normalize-temps $HISTORY  \
  | json -e "this.medtronic = 'mm://openaps/$self/' + (this._type || this.eventType);" \
    -e "this.created_at = this.created_at ? this.created_at : this.timestamp" \
    -e "this.enteredBy = 'openaps://medtronic/$model'" \
    -e "if (this.glucose && !this.glucoseType && this.glucose > 0) { this.glucoseType = this.enteredBy }" \
    -e "this.eventType = (this.eventType ?  this.eventType : 'Note')" \
    -e "if (this._type == 'AlarmSensor' && this.alarm_description) {this.notes = this.alarm_description}" \
    -e "if (this.eventType == 'Note' && !this.alarm_description) { this.notes = this._type + ' $model ' + (this.notes ? this.notes : '')}" \
     > $OUTPUT

