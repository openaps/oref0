#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self --find <NIGHTSCOUT_HOST> <API_SECREAT> <number_of_days>- No-op version, find out what delete would do.
$self delete <NIGHTSCOUT_HOST>  <API_SECREAT> <number_of_days> - move  entries from NIGHTSCOUT_HOST devicestatus collection to "$HOME/myopenaps/backup
$self nightly <number_of_days> - move  entries from NIGHTSCOUT_HOST devicestatus collection to "$HOME/myopenaps/backup
EOF

function write_backup() {
json -a -o jsony-0 >> $BACKUP_DIR/devicestatus.txt
}

export API_SECRET
test -n "$3" && API_SECRET=$(nightscout hash-api-secret $3)
test -n "$4" && NUM_DAYS=$4
BACKUP_DIR="$HOME/myopenaps"/backup
mkdir -p $BACKUP_DIR

ENDPOINT=$2/api/v1/devicestatus

if [ $1 = "nightly" ]; then
   test -n "$2" && NUM_DAYS=$2
   ENDPOINT=$NIGHTSCOUT_HOST/api/v1/devicestatus
fi

if [[ -z "$API_SECRET" || -z "$NUM_DAYS" ]] ; then
  test -z "$API_SECRET" && echo API_SECRET undefined.
  test -z "$NUM_DAYS" && echo NUM_DAYS undefined.
  print_usage
  exit 1;
fi

date_string=$(date -d "-$NUM_DAYS days" +%Y-%m-%d)
fetch_cmd="curl  --compressed -s -g $ENDPOINT.json?find\[created_at\]\[\\"\$"lte\]=$date_string\&count=100000"
delete_cmd="curl -X DELETE -H \"API-SECRET: $API_SECRET\"  -s -g $ENDPOINT.json?find\[created_at\]\[\\"\$"lte\]=$date_string\&count=100000"

case "$1" in
  --find)
    echo $fetch_cmd
    echo $delete_cmd
    ;;
  delete)
    #echo $fetch_cmd
    #echo $delete_cmd
    eval $fetch_cmd | write_backup
    eval $delete_cmd
    ;;
  nightly)
    #echo $fetch_cmd
    #echo $delete_cmd
    eval $fetch_cmd | write_backup
    eval $delete_cmd
    ;;
  *|help|--help|-h)
    print_usage
    exit 1;
    ;;
esac
