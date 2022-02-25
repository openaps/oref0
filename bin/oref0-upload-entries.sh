#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self
Upload data to Nightscout. Normally runs from crontab.
EOF


echo "Checking entries-last-date.json..."
if [ -e upload/entries-last-date.json ]; then
    LAST_TIME=$(jq -s ".[0].date" upload/entries-last-date.json)
    echo "LAST_TIME is $LAST_TIME"
    if [ "$LAST_TIME" == "null" ]; then
        echo "Setting LAST_TIME to 0"
        LAST_TIME=0
    fi
else
    echo "Setting LAST_TIME to 0"
    LAST_TIME=0
fi

echo "Merging cgm-glucose.json and entries-upload.json"
jq -s --unbuffered "[.[0][]] + [.[1][]]|unique|reverse" cgm/cgm-glucose.json upload/entries-upload.json > upload/entries-upload.new.json

echo "Selecting only those records newer than $LAST_TIME"
jq -s --unbuffered --arg lasttime "$LAST_TIME" '.[0][] | select(.date > ("\($lasttime)" | tonumber))' upload/entries-upload.new.json > upload/entries-upload.array.json

echo "Merging to an array and removing intermediate files"
jq -s --unbuffered "[.[]]" upload/entries-upload.array.json > upload/entries-upload.json
rm upload/entries-upload.new.json upload/entries-upload.array.json

UPLOAD_COUNT=$(jq -s ".[]|length" upload/entries-upload.json)
echo "Entries to upload: $UPLOAD_COUNT"
if (( $UPLOAD_COUNT )); then
    (ns-upload $NIGHTSCOUT_HOST $API_SECRET entries upload/entries-upload.json - && jq -s "{\"date\":.[0][0].date}" upload/entries-upload.json > upload/entries-last-date.json && rm upload/entries-upload.json)
fi
