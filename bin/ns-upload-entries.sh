#!/bin/bash

# Author: Ben West
# Maintainer: @cjo20, @scottleibrand

ENTRIES=${1-entries.json}
NIGHTSCOUT_HOST=${NIGHTSCOUT_HOST-localhost:1337}
#TZ=${3-$(date +%z)}
OUTPUT=${2}

export ENTRIES API_SECRET NIGHTSCOUT_HOST
# requires API_SECRET and NIGHTSCOUT_HOST to be set in calling environment (i.e. in crontab)
(
curl -s -X POST --data-binary @$ENTRIES \
  -H "API-SECRET: $API_SECRET" \
  -H "content-type: application/json" \
  $NIGHTSCOUT_HOST/api/v1/entries.json
) && ( test -n "$OUTPUT" && touch $OUTPUT ; logger "Uploaded $ENTRIES to $NIGHTSCOUT_HOST" ) || logger "Unable to upload to $NIGHTSCOUT_HOST"

