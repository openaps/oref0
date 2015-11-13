#!/bin/bash

# Author: Ben West

self=$(basename $0)
NIGHTSCOUT_HOST=${NIGHTSCOUT_HOST-${1-localhost:1337}}
API_SECRET=${2-${API_SECRET}}
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
  --config)
    test -z $3 && usage && exit 1;
    # echo openaps device add $2 process $self $3
API_SECRET=$(echo -n $3 | sha1sum | cut -d ' ' -f 1 | tr -d "\n")
    cat <<EOF
openaps device add $self process --require "type report" $self "$self-NIGHTSCOUT" "$self-APIKEY"
sed -i -e "s/$self-NIGHTSCOUT/$2/g" $self.ini
sed -i -e "s/$self-APIKEY/$API_SECRET/g" $self.ini
openaps report add $6 text $self shell "$4" "$5"
EOF
    exit 0;
    ;;
  help)
    usage
    ;;
  *)
    # curl -s $REPORT_ENDPOINT | json
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
(test "$ENTRIES" != "-" && cat $ENTRIES || cat )| (
curl -s -X POST --data-binary @- \
  -H "API-SECRET: $API_SECRET" \
  -H "content-type: application/json" \
  $REST_ENDPOINT
) && ( test -n "$OUTPUT" && touch $OUTPUT ; logger "Uploaded $ENTRIES to $NIGHTSCOUT_HOST" ) || logger "Unable to upload to $NIGHTSCOUT_HOST"

