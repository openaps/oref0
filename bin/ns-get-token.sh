#!/bin/bash

# Author: Ben West

self=$(basename $0)
REPORT=${1-entries.json}
# NIGHTSCOUT_HOST is stored in $HOME/myopenaps/ns.ini
# Proxy on 1338 will be used to store request to Nightscout and to use the token authentication
NIGHTSCOUT_HOST=http://localhost:1338
QUERY=${3}
OUTPUT=${4-/dev/fd/1}

CURL_FLAGS="--compressed -g -s"
NIGHTSCOUT_FORMAT=${NIGHTSCOUT_FORMAT-json}
test "$NIGHTSCOUT_DEBUG" = "1" && CURL_FLAGS="${CURL_FLAGS} -iv"
test "$NIGHTSCOUT_DEBUG" = "1" && set -x

function usage ( ) {
cat <<EOF
Usage: $self <entries.json> [NIGHTSCOUT_HOST|localhost:1338] [QUERY] [stdout|-]

$self type <entries.json> <NIGHTSCOUT_HOST|localhost:1338] [QUERY] [stdout|-]
$self host <NIGHTSCOUT_HOST|localhost:1337> <entries.json> [QUERY] [stdout|-]

EOF
}
REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${QUERY}
case $1 in
  host)
    # $self
    REPORT=${3-entries.json}
    QUERY=${4}
    OUTPUT=${5-/dev/fd/1}
    REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${QUERY}
    test -z "$NIGHTSCOUT_HOST" && usage && exit 1;
    
    curl ${CURL_FLAGS} $REPORT_ENDPOINT | $NIGHTSCOUT_FORMAT

    ;;
  type)
    shift
    exec $self $*
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    test -z "$NIGHTSCOUT_HOST" && usage && exit 1;
    curl ${CURL_FLAGS} $REPORT_ENDPOINT | $NIGHTSCOUT_FORMAT
    ;;
esac


