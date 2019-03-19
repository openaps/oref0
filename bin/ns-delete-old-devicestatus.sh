#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self --find <NIGHTSCOUT_HOST> <asn1 of API_SECREAT>- No-op version, find out what delete would do.
$self delete <NIGHTSCOUT_HOST>  <asn1 of API_SECREAT>- Delete duplicate entries from ${NIGHTSCOUT_HOST-<NIGHTSCOUT_HOST>}
EOF

function fetch ( ) {
  two_month_ago=$(date -d "-2 month" +%Y-%m-%d)
  curl  --compressed -s -g $ENDPOINT.json?find\[created_at\]\[\$lte\]=$two_month_ago\&count=100000
}

function get_tid ( ) {
  json -a _id created_at
}


function debug_cmd ( ) {
tid=$1
created_at=$2
echo -n  curl -X DELETE -H "API-SECRET: $API_SECRET" -g ${ENDPOINT}.json?find[_id]=$tid\&find[created_at][\$eq]=$created_at
}

function delete_cmd ( ) {
tid=$1
created_at=$2
(set -x
curl -X DELETE -H "API-SECRET: $API_SECRET" -g ${ENDPOINT}.json?find[_id]=$tid\&find[created_at][\$eq]=$created_at
)
}


function main ( ) {
NIGHTSCOUT_HOST=$1
ACTION=${2-debug_cmd}
ENDPOINT=${NIGHTSCOUT_HOST}/api/v1/devicestatus

if [[ -z "$NIGHTSCOUT_HOST" || -z "$NIGHTSCOUT_HOST" ]] ; then
  test -z "$NIGHTSCOUT_HOST" && echo NIGHTSCOUT_HOST undefined.
  test -z "$API_SECRET" && echo API_SECRET undefined.
  print_usage
  exit 1;
fi

export NIGHTSCOUT_HOST ENDPOINT
fetch | get_tid | while read tid created_at line ; do
    echo $tid $created_at
    $ACTION $tid $created_at
    echo
done


}

export API_SECRET
test -n "$3" && API_SECRET=$3
case "$1" in
  --find)
    main $2
    ;;
  delete)
    main $2 delete_cmd
    ;;
  *|help|--help|-h)
    print_usage
    exit 1;
    ;;
esac
