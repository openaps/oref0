#!/usr/bin/env bash

# Author: Ben West

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

NIGHTSCOUT_HOST=${NIGHTSCOUT_HOST-${1-localhost:1337}}
API_SECRET=${2-${API_SECRET}}
TYPE=${3-entries.json}
ENTRIES=${4-entries.json}
OUTPUT=${5}

REST_ENDPOINT="${NIGHTSCOUT_HOST}/api/v1/${TYPE}"

usage "$@" <<EOF
Usage: $self <NIGHTSCOUT_HOST|localhost:1337> <API_SECRET> [API-TYPE|entries.json] <monitor/entries-to-upload.json> [stdout|-]

$self help - This message.
EOF

export ENTRIES API_SECRET NIGHTSCOUT_HOST REST_ENDPOINT
if [[ -z $API_SECRET ]] ; then
  echo "$self: missing API_SECRET"
  test -z "$NIGHTSCOUT_HOST" && echo "$self: also missing NIGHTSCOUT_HOST"
  print_usage > /dev/fd/2
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
    curl --compressed -m 30 -s -X POST --data-binary @- \
        -H "content-type: application/json" \
        $REST_ENDPOINT
    ) && ( test -n "$OUTPUT" && touch $OUTPUT ; logger "Uploaded $ENTRIES to $NIGHTSCOUT_HOST" ) || ( logger "Unable to upload to $NIGHTSCOUT_HOST"; exit 2 )
else
    (test "$ENTRIES" != "-" && cat $ENTRIES || cat )| (
    curl --compressed -m 30 -s -X POST --data-binary @- \
        -H "API-SECRET: $API_SECRET" \
        -H "content-type: application/json" \
        $REST_ENDPOINT
    ) && ( test -n "$OUTPUT" && touch $OUTPUT ; logger "Uploaded $ENTRIES to $NIGHTSCOUT_HOST" ) || ( logger "Unable to upload to $NIGHTSCOUT_HOST"; exit 2 )
fi
