#!/bin/bash

# Author: Ben West, Maintainer: Scott Leibrand

HISTORY=${1-pumphistory.json}
OUTPUT=${2-pumphistory.ns.json}
#TZ=${3-$(date +%z)}

cat $HISTORY | \
  json -e "this.medtronic = this._type;" | \
  #json -e "this.dateString = this.timestamp + '$(TZ=TZ date +%z)'" | \
  json -e "this.dateString = this.timestamp + '$(date +%z)'" | \
  json -e "this.type = 'medtronic'" | \
  json -e "this.date = this.date ? this.date : new Date(Date.parse(this.dateString)).getTime( )" \
  > $OUTPUT


# requires API_SECRET and NIGHTSCOUT_HOST to be set in calling environment (i.e. in crontab)
curl -s -X POST --data-binary @$OUTPUT -H "API-SECRET: $API_SECRET" -H "content-type: application/json" $NIGHTSCOUT_HOST/api/v1/entries.json >/dev/null && ( touch /tmp/openaps.online && echo "Uploaded $OUTPUT to $NIGHTSCOUT_HOST" ) || echo "Unable to upload to $NIGHTSCOUT_HOST"
