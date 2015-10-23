#!/bin/bash

# Author: Ben West

HISTORY=${1-monitor/pump-history-zoned.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}
self=$(basename $0)

# | json -e "this.type = 'mm://openaps/$self'" \

oref0-normalize-temps $HISTORY  \
  | json -e "this.medtronic = 'mm://openaps/$self/' + (this._type || this.eventType);" \
  | json -e "this.created_at = this.created_at ? this.created_at : this.timestamp" \
  | json -e "this.enteredBy = 'openaps://medtronic'" \
  | json -e "this.eventType = (this.eventType ?  this.eventType : 'Note')" \
  | json > $OUTPUT


