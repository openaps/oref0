#!/bin/bash

# Author: Ben West

self=$(basename $0)
NIGHTSCOUT_HOST=${NIGHTSCOUT_HOST-${1-localhost:1337}}
# QUERY=${3}
REPORT=${2-entries.json}
OUTPUT=${3-/dev/fd/1}

function usage ( ) {
cat <<EOF
Usage: $self <NIGHTSCOUT_HOST|localhost:1337> [entries.json] [stdout|-]

$self --config <NIGHTSCOUT_HOST> <entries.json> monitor/entries.json
EOF
}

REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/$REPORT
case $1 in
  --config)
    test -z $3 && usage && exit 1;
    # echo openaps device add $2 process $self $3
    cat <<EOF
openaps device add $self process --require report $self $2
openaps report add $4 text $self shell "$3"
EOF
    exit 0;
    ;;
  --noop)
    echo "curl -s $REPORT_ENDPOINT | json"
    ;;
  help)
    usage
    ;;
  *)
    curl -s $REPORT_ENDPOINT | json
    ;;
esac


