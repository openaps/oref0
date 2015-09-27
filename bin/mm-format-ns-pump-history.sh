#!/bin/bash

# Author: Ben West
# Maintainer: Scott Leibrand

HISTORY=${1-pumphistory.json}
OUTPUT=${2-/dev/fd/1}
#TZ=${3-$(date +%z)}

cat $HISTORY | \
  json -e "this.medtronic = this._type;" | \
  #json -e "this.dateString = this.timestamp + '$(TZ=TZ date +%z)'" | \
  json -e "this.dateString = this.timestamp + '$(date +%z)'" | \
  json -e "this.type = 'medtronic'" | \
  json -e "this.date = this.date ? this.date : new Date(Date.parse(this.dateString)).getTime( )" \
  > $OUTPUT


