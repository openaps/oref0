#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self --find <NIGHTSCOUT_HOST> <API_SECREAT> <number_of_days>- No-op version, find out what delete would do.
$self delete <NIGHTSCOUT_HOST>  <API_SECREAT> <number_of_days> - move  entries from NIGHTSCOUT_HOST devicestatus collection to "$HOME/myopenaps/backup
$self nightly <number_of_days> - move  entries from NIGHTSCOUT_HOST devicestatus collection to "$HOME/myopenaps/backup
EOF

function fetch ( ) {
  date_string=$(date -d "-$NUM_DAYS days" +%Y-%m-%d)
  curl  --compressed -s -g $ENDPOINT.json?find\[created_at\]\[\$lte\]=$date_string\&count=10000
}

function get_tid ( ) {
  json -a _id created_at
}

function write_backup() {
tee >(json -a >> $BACKUP_DIR/devicestatus.txt) 
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
NUM_DAYS=$2
ACTION=$3
ENDPOINT=${NIGHTSCOUT_HOST}/api/v1/devicestatus

if [[ -z "$NIGHTSCOUT_HOST" || -z "$API_SECRET" || -z "$NUM_DAYS" ]] ; then
  test -z "$NIGHTSCOUT_HOST" && echo NIGHTSCOUT_HOST undefined.
  test -z "$API_SECRET" && echo API_SECRET undefined.
  test -z "$NUM_DAYS" && echo NUM_DAYS undefined.
  print_usage
  exit 1;
fi

export NIGHTSCOUT_HOST ENDPOINT NUM_DAYS
fetch | write_backup | get_tid | while read tid created_at line ; do
   echo $tid $created_at
    $ACTION $tid $created_at
    echo
done


}

export API_SECRET
test -n "$3" && API_SECRET=$(nightscout hash-api-secret $3)
test -n "$4" && NUM_DAYS=$4
BACKUP_DIR="$HOME/myopenaps"/backup
mkdir -p $BACKUP_DIR
case "$1" in
  --find)
    main $2 $NUM_DAYS debug_cmd
    ;;
  delete)
    main $2 $NUM_DAYS delete_cmd
    ;;
  nightly)
    test -n "$2" && NUM_DAYS=$2
    main $NIGHTSCOUT_HOST $NUM_DAYS delete_cmd
    ;;
  *|help|--help|-h)
    print_usage
    exit 1;
    ;;
esac
