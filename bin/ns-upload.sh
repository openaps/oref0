#!/bin/bash

# Author: Ben West

self=$(basename $0)
NIGHTSCOUT_HOST=${NIGHTSCOUT_HOST-${1-localhost:1337}}
API_SECRET=${2-${API_SECRET}}
TYPE=${3-entries.json}
ENTRIES=${4-entries.json}
OUTPUT=${5}

REST_ENDPOINT="${NIGHTSCOUT_HOST}/api/v1/${TYPE}"

function usage ( ) {
cat <<EOF
Usage: $self <NIGHTSCOUT_HOST|localhost:1337> <API_SECRET> [API-TYPE|entries.json] <monitor/entries-to-upload.json> [stdout|-]

$self help - This message.
EOF
}

case $1 in
  help)
    usage
    ;;
  *)
    # curl -s ${REPORT_ENDPOINT} | json
    ;;
esac

export ENTRIES API_SECRET NIGHTSCOUT_HOST REST_ENDPOINT
if [[ -z $API_SECRET ]] ; then
  echo "$self: missing API_SECRET"
  test -z "$NIGHTSCOUT_HOST" && echo "$self: also missing NIGHTSCOUT_HOST"
  usage > /dev/fd/2
  cat <<EOF > /dev/fd/2
Usage: $self <NIGHTSCOUT_HOST-http://localhost:1337> <API_SECRET> [entries|treatments|profile/] <file-to-upload.json> 
EOF
  exit 1;
fi
# requires API_SECRET and NIGHTSCOUT_HOST to be set in calling environment
# (i.e. in crontab)
if [[ "$ENTRIES" != "-" ]] ; then
  if [[ ! -f $ENTRIES ]] ; then
    echo "Input file $ENTRIES" does not exist.
    exit 1;
  fi
fi

# use token authentication if the user has a token set in their API_SECRET environment variable
if [[ "${API_SECRET,,}" =~ "token=" ]]; then
  REST_ENDPOINT="${REST_ENDPOINT}?${API_SECRET}"
    (test "$ENTRIES" != "-" && cat $ENTRIES || cat )| (
    curl -m 30 -s -X POST --data-binary @- \
        -H "content-type: application/json" \
        $REST_ENDPOINT
    ) && ( test -n "$OUTPUT" && touch $OUTPUT ; logger "Uploaded $ENTRIES to $NIGHTSCOUT_HOST" ) || logger "Unable to upload to $NIGHTSCOUT_HOST"
else
    (test "$ENTRIES" != "-" && cat $ENTRIES || cat )| (
    curl -m 30 -s -X POST --data-binary @- \
        -H "API-SECRET: $API_SECRET" \
        -H "content-type: application/json" \
        $REST_ENDPOINT
    ) && ( test -n "$OUTPUT" && touch $OUTPUT ; logger "Uploaded $ENTRIES to $NIGHTSCOUT_HOST" ) || logger "Unable to upload to $NIGHTSCOUT_HOST"
fi
