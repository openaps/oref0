#!/bin/bash

# Author: Ben West

self=$(basename $0)
REPORT=${1-entries.json}
NIGHTSCOUT_HOST=${NIGHTSCOUT_HOST-${2-localhost:1337}}
QUERY=${3}
OUTPUT=${4-/dev/fd/1}

CURL_FLAGS="--compressed -g -s"
NIGHTSCOUT_FORMAT=${NIGHTSCOUT_FORMAT-json}
test "$NIGHTSCOUT_DEBUG" = "1" && CURL_FLAGS="${CURL_FLAGS} -iv"
test "$NIGHTSCOUT_DEBUG" = "1" && set -x

function usage ( ) {
cat <<EOF
Usage: $self <entries.json> [NIGHTSCOUT_HOST|localhost:1337] [QUERY] [stdout|-]

$self type <entries.json> <NIGHTSCOUT_HOST|localhost:1337] [QUERY] [stdout|-]
$self host <NIGHTSCOUT_HOST|localhost:1337> <entries.json> [QUERY] [stdout|-]

EOF
}

CURL_AUTH=""

# use token authentication if the user has a token set in their API_SECRET environment variable
if [[ "${API_SECRET}" =~ "token=" ]]; then
  if [[ -z ${QUERY} ]]; then
    REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${API_SECRET}
  else
    REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${API_SECRET}'&'${QUERY}
  fi
else
  REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${QUERY}
  CURL_AUTH='-H "api-secret: ${API_SECRET}"'
fi

case $1 in
  host)
    # $self
    NIGHTSCOUT_HOST=${NIGHTSCOUT_HOST-${2-localhost:1337}}
    REPORT=${3-entries.json}
    QUERY=${4}
    OUTPUT=${5-/dev/fd/1}

    # use token authentication if the user has a token set in their API_SECRET environment variable
    if [[ "${API_SECRET}" =~ "token=" ]]; then
      if [[ -z ${QUERY} ]]; then
        REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${API_SECRET}
      else
        REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${API_SECRET}'&'${QUERY}
      fi
    else
      REPORT_ENDPOINT=$NIGHTSCOUT_HOST/api/v1/${REPORT}'?'${QUERY}
    fi
    test -z "$NIGHTSCOUT_HOST" && usage && exit 1;

    curl ${CURL_AUTH} ${CURL_FLAGS} $REPORT_ENDPOINT | $NIGHTSCOUT_FORMAT

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
    curl ${CURL_AUTH} ${CURL_FLAGS} $REPORT_ENDPOINT | $NIGHTSCOUT_FORMAT
    ;;
esac


