#!/bin/bash

# Author: Ben West

self=$(basename $0)
NIGHTSCOUT_HOST=http://localhost:1338
API_SECRET="DEPRECATED_USE_TOKENS"
TYPE=${3-entries.json}
ENTRIES=${4-entries.json}
#TZ=${3-$(date +%z)}
OUTPUT=${5}

REST_ENDPOINT="${NIGHTSCOUT_HOST}/api/v1/${TYPE}"

function usage ( ) {
cat <<EOF
Usage: $self <NIGHTSCOUT_HOST|localhost:1337> <API_SECRET> [API-TYPE|entries.json] <monitor/entries-to-upload.json> [stdout|-]

$self --config <NIGHTSCOUT_HOST> <PLAIN_API_SECRET> <API-TYPE|entries.json> <monitor/entries-to-upload.json> output-report.json

$self help - This message.
EOF
}

case $1 in
  help)
    usage
    ;;
  *)
    # curl -s $REPORT_ENDPOINT | json
    ;;
esac
export ENTRIES NIGHTSCOUT_HOST REST_ENDPOINT
if [[ "$ENTRIES" != "-" ]] ; then
  if [[ ! -f $ENTRIES ]] ; then
    echo "Input file $ENTRIES" does not exist.
    exit 1;
  fi
fi
(test "$ENTRIES" != "-" && cat $ENTRIES || cat )| (
curl -m 30 -s -X POST --data-binary @- \
  -H "content-type: application/json" \
  $REST_ENDPOINT
) && ( test -n "$OUTPUT" && touch $OUTPUT ; logger "Uploaded $ENTRIES to $NIGHTSCOUT_HOST" ) || logger "Unable to upload to $NIGHTSCOUT_HOST"

