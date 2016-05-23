#!/bin/bash


self=$(basename $0)
NAME=${1-help}
shift
PROGRAM="ns-${NAME}"
COMMAND=$(which $PROGRAM | head -n 1)
NIGHTSCOUT_DEBUG=${NIGHTSCOUT_DEBUG-0}

function help_message ( ) {
  cat <<EOF
  Usage:
$self <cmd>

* latest-openaps-treatment
* cull-latest-openaps-treatments

* get
* upload
* dedupe-treatments
* hash-api-secret
* status
* upload-entries
* autoconfigure-device-crud

EOF
}

function setup_help ( ) {

cat <<EOF
$self autoconfigure-device-crud <NIGHTSCOUT_HOST> <API_SECRET>

sets up:
openaps use ns shell get entries.json 'count=10'
openaps use ns shell upload treatments.json recently/combined-treatments.json
EOF
}

function ns_help ( ) {
cat <<EOF
TODO: improve help
openaps use ns shell get entries.json 'count=10'
openaps use ns shell upload treatments.json recently/combined-treatments.json

  -h                                  This message.
  get type args                                  Get records of type from
                                                 Nightscout matching args.

  upload endpoint file                           Upload a file to the Nightscout endpoint.
  latest-treatment-time                          - get latest treatment time from Nightscout
  format-recent-history-treatments history model - Formats medtronic pump
                                                 history and model into
                                                 Nightscout compatible
                                                 treatments.

  format-recent-type ZONE type file              - Selects elements from the
                                                 file where the elements would
                                                 satisfy a gap in the last 1000
                                                 Nightscout records.

  upload-non-empty-treatments file               - Upload a non empty treatments
                                                 file to Nightscout.
  lsgaps tz entries                              - Re-use openaps timezone device
                                                 to find gaps in a type (entries)
                                                 by default.
  upload-non-empty-type type file
  status                                         - Retrieve status
  preflight                                      - NS preflight
EOF
}
case $NAME in
latest-openaps-treatment)
  ns-get treatments.json'?find[enteredBy]=/openaps:\/\//&count=1' $* | json 0
  ;;
ns)
  NIGHTSCOUT_HOST=$1
  API_SECRET=$2
  OP=$3
  shift
  shift
  shift

  case $OP in
    -h|--help|help)
    ns_help
    exit 0
    ;;
    get)
    exec ns-get host $NIGHTSCOUT_HOST $*
    exit 0
    ;;
    preflight)
      STATUS=$(ns-get host $NIGHTSCOUT_HOST status.json | json status)
      if [[ $STATUS = "ok" ]] ; then
        echo "true" | json -j
        exit 0
      else
        echo "false" | json -j
        exit 1
      fi
    ;;
    status)
      ns-get host $NIGHTSCOUT_HOST status.json | json
    ;;
    lsgaps)
      ZONE=${1-'tz'}
      TYPE=${2-'entries'}
      ns-get host $NIGHTSCOUT_HOST "${TYPE}.json" 'count=300' \
        | openaps use $ZONE  \
          rezone --astimezone --date dateString - \
        | openaps use $ZONE  \
          lsgaps --minutes 5 --after now  --date dateString -


    ;;
    format-recent-type)
      ZONE=${1-'tz'}
      TYPE=${2-'entries'}
      FILE=${3-''}
      # nightscout ns $NIGHTSCOUT_HOST $API_SECRET
      test -z ${ZONE} && "Missing first argument, ZONE, usually is set to tz" && exit 1
      test -z ${TYPE} && "Missing second argument, TYPE, one of: entries, treatments, devicestatus, profiles." && exit 1
      test ! -e ${FILE} && "Third argument, contents to upload, FILE, does not exist" && exit 1
      test ! -r ${FILE} && "Third argument, contents to upload, FILE, not readable." && exit 1
      openaps use ns shell lsgaps ${ZONE} ${TYPE} \
        |  openaps use ${ZONE} select --current now --gaps - ${FILE}  | json
    ;;
    latest-entries-time)
      PREVIOUS_TIME=$(ns-get host $NIGHTSCOUT_HOST entries.json 'find[type]=sgv'  | json 0)
      test -z "${PREVIOUS_TIME}" && echo -n 0 || echo $PREVIOUS_TIME | json -j dateString
      exit 0
    ;;
    latest-treatment-time)
      PREVIOUS_TIME=$(ns-get host $NIGHTSCOUT_HOST treatments.json'?find[enteredBy]=/openaps:\/\//&count=1'  | json 0)
      test -z "${PREVIOUS_TIME}" && echo -n 0 || echo $PREVIOUS_TIME | json -j created_at
      exit 0
    # exec ns-get host $NIGHTSCOUT_HOST $*
    ;;
    format-recent-history-treatments)
      HISTORY=$1
      MODEL=$2
      LAST_TIME=$(nightscout ns $NIGHTSCOUT_HOST $API_SECRET latest-treatment-time | json)
      exec nightscout cull-latest-openaps-treatments $HISTORY $MODEL ${LAST_TIME}
      exit 0

    ;;
    upload-non-empty-type)
      TYPE=${1-entries.json}
      FILE=$2
      test $(cat $FILE | json -a | wc -l) -lt 1 && echo "Nothing to upload." > /dev/stderr && cat $FILE && exit 0
      exec ns-upload $NIGHTSCOUT_HOST $API_SECRET $TYPE $FILE
    ;;
    upload-non-empty-treatments)
      test $(cat $1 | json -a | wc -l) -lt 1 && echo "Nothing to upload." > /dev/stderr && cat $1 && exit 0
    exec ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json $1

    ;;
    upload)
    exec ns-upload $NIGHTSCOUT_HOST $API_SECRET $*
    ;;
    *)
    echo "Unknown request:" $OP
    ns_help
    exit 1;
    ;;
  esac
    exit 0

  ;;
hash-api-secret)
  if [[ -z "$1" ]] ; then
    echo "Missing plain Nightscout passphrase".
    echo "Usage: $self hash-api-secret 'myverylongsecret'".
    exit 1;
  fi
  API_SECRET=$(echo -n $1 | sha1sum | cut -d ' ' -f 1 | tr -d "\n")
  echo $API_SECRET
  ;;
autoconfigure-device-crud)
  NIGHTSCOUT_HOST=$1
  PLAIN_NS_SECRET=$2
  API_SECRET=$($self hash-api-secret $2)
  case $1 in
    help|-h|--help)
      setup_help
      exit 0
      ;;
  esac
  # openaps device add ns-get host
  test -z "$NIGHTSCOUT_HOST" && setup_help && exit 1;
  test -z "$API_SECRET" && setup_help && exit 1;
  openaps device add ns process --require "oper" nightscout ns "NIGHTSCOUT_HOST" "API_SECRET"
  openaps device show ns --json | json \
    | json -e "this.extra.args = this.extra.args.replace(' NIGHTSCOUT_HOST ', ' $NIGHTSCOUT_HOST ')" \
    | json -e "this.extra.args = this.extra.args.replace(' API_SECRET', ' $API_SECRET')" \
    | openaps import
  ;;
cull-latest-openaps-treatments)
  INPUT=$1
  MODEL=$2
  LAST_TIME=$3
  mm-format-ns-treatments $INPUT $MODEL |  json -c "this.created_at > '$LAST_TIME'"
  ;;
help|--help|-h)
  help_message
  exit 0
  ;;
*)
  test -n "$COMMAND" && exec $COMMAND $*
  ;;
esac
