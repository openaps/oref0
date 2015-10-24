#!/bin/bash

# Author: Ben West

HISTORY=${1-monitor/pump-history-zoned.json}
MODEL=${2-model.json}
OUTPUT=${3-/dev/fd/1}
#TZ=${3-$(date +%z)}
self=$(basename $0)

# | json -e "this.type = 'mm://openaps/$self'" \
model=$(json -f $MODEL)

oref0-normalize-temps $HISTORY  \
  | json -e "this.medtronic = 'mm://openaps/$self/' + (this._type || this.eventType);" \
  | json -e "this.created_at = this.created_at ? this.created_at : this.timestamp" \
  | json -e "this.enteredBy = 'openaps://medtronic/$model'" \
  | json -e "if (this.glucose && !this.glucoseType && this.glucose > 0) { this.glucoseType = this.enteredBy }" \
  | json -e "this.eventType = (this.eventType ?  this.eventType : 'Note')" \
  | json -e "if (this.eventType == 'Note') { this.notes = this._type + ' $model ' + (this.notes ? this.notes : '')}" \
  | json > $OUTPUT


