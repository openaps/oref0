#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

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
* get-status
* upload-entries
* autoconfigure-device-crud

EOF

extra_ns_help

}

function extra_ns_help ( ) {

cat <<EOF
## Nightscout Endpoints

* entries.json - Glucose values, mbgs, sensor data.
* treatments.json - Pump history, bolus, treatments, temp basals.
* devicestatus.json - Battery levels, reservoir.
* profile.json - Planned rates/settings/ratios/sensitivities.
* status.json  - Server status.

## Examples


### Get records from Nightscout

Use the get feature which takes two arguments: the name of the endpoint
(entries, devicestatus, treatments, profiles) and any query arguments to append
to the argument string. 'count=10' is a reasonable debugging value.
The query-params can be used to generate any query Nightscout can respond to.

    openaps use ns shell get \$endpoint \$query-params

### Unifying pump treatments in Nightscout

To upload treatments data to Nightscout, prepare you zoned glucose, and pump
model reports, and use the following two reports:

    openaps report add nightscout/recent-treatments.json JSON ns shell  format-recent-history-treatments monitor/pump-history.json model.json
    openaps report add nightscout/uploaded.json JSON  ns shell upload-non-empty-treatments  nightscout/recent-treatments.json

Here are the equivalent uses:

    openaps use ns shell format-recent-history-treatments monitor/pump-history.json model.json
    openaps use ns shell upload-non-empty-treatments nightscout/recent-treatments.json

The first report runs the format-recent-history-treatments use, which fetches
data from Nightscout and determines which of the latest deltas from openaps
need to be sent. The second one uses the upload-non-empty-treatments use to
upload treatments to Nightscout, if there is any data to upload.

### Uploading glucose values to Nightscout

Format potential entries (glucose values) for Nightscout.

    openaps use ns shell format-recent-type tz entries monitor/glucose.json  | json -a dateString | wc -l
    # Add it as a report
    openaps report add nightscout/recent-missing-entries.json JSON ns shell format-recent-type tz entries monitor/glucose.json
    # fetch data for first time
    openaps report invoke nightscout/recent-missing-entries.json

    # add report for uploading to NS
    openaps report add nightscout/uploaded-entries.json JSON  ns shell upload entries.json nightscout/recent-missing-entries.json
    # upload for fist time.
    openaps report invoke nightscout/uploaded-entries.json
EOF
}
function setup_help ( ) {

cat <<EOF
$self autoconfigure-device-crud <NIGHTSCOUT_HOST> <API_SECRET>

sets up:
openaps use ns shell get entries.json 'count=10'
openaps use ns shell upload treatments.json recently/combined-treatments.json



EOF
extra_ns_help
}

function ns_help ( ) {
cat <<EOF

openaps use ns shell get entries.json 'count=10'
openaps use ns shell upload treatments.json recently/combined-treatments.json

  -h                                  This message.
  get type args                                  Get records of type from
                                                 Nightscout matching args.

  oref0_glucose [tz] [args]                      Get records matching oref0
                                                 requirements according to args
                                                 from Nightscout.
                                                 tz should be the name of the
                                                 timezones device (default with
                                                 no args is tz).
                                                 args are ampersand separated
                                                 arguments to append to the
                                                 search query for Nightscout.
  oref0_glucose_without_zone [args]              Like oref0_glucose but without
                                                 rezoning.
  oref0_glucose_since expr [tz] [count]          Get records matching oref0
                                                 requirements filtered by a date calculated by expr
                                                 from Nightscout.
                                                 expr is used with date -d, for example -6hours.
                                                 tz should be the name of the
                                                 timezones device (default with
                                                 no args is tz).
                                                 count is the max count (needed to overide NS default of 10).
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
  status                                         - ns-status
  get-status                                     - status - get NS status
  preflight                                      - NS preflight
  temp_targets [expr]                            - Get temp target treatments from Nightscout
                                                 expr is used with date -d, default is -24hours.
  carb_history [expr]                            - Get treatments with carbs from Nightscout
                                                 expr is used with date -d, default is -24hours.
EOF
extra_ns_help
}
case $NAME in
latest-openaps-treatment)
  ns-get treatments.json'?find[enteredBy]=/openaps:\/\//&count=1' $* | jq .[0]
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
      STATUS=$(ns-get host $NIGHTSCOUT_HOST status.json | jq -r .status)
      if [[ $STATUS = "ok" ]] ; then
        echo true
        exit 0
      else
        echo false
        exit 1
      fi
    ;;
    get-status)
      ns-get host $NIGHTSCOUT_HOST status.json | jq .
    ;;
    status)
      ns-status $*
    ;;
    lsgaps)
      ZONE=${1-'tz'}
      TYPE=${2-'entries'}
      ns-get host $NIGHTSCOUT_HOST "${TYPE}.json" 'count=300' \
        | openaps use $ZONE  \
          rezone --astimezone --date dateString - \
        | openaps use $ZONE  \
          lsgaps --minutes 6 --after now  --date dateString -


    ;;
    mm-format-ns-glucose)
      #Format Medtronic glucose data into something acceptable to Nightscout.
      HISTORY=$1
      cat $HISTORY | \
        jq '[ .[]
          | .sgv = if .sgv then .sgv else .glucose end
          | if has("_type") then .medtronic = ._type else . end
          | if .dateString | not then .dateString = .display_time else . end
          | if ( ( .dateString | not ) and ( .date | tostring | test(":") ) ) then
            .dateString = ( [ .date, "'$(date +%z)'" ] | join("") ) else . end
          | ( .dateString | sub("Z"; "") | split(".") )[0] as $time
          | ( ( .dateString | sub("Z"; "") | split(".") )[1] | tonumber ) as $msec
          | .date = ( ( [ $time, "Z" ] | join("") ) | fromdateiso8601 ) * 1000 + $msec
          | .type = if .name and (.name | test("GlucoseSensorData")) then "sgv" else "pumpdata" end
          | .device = "openaps://medtronic/pump/cgm" ]'
    ;;
    format-recent-type)
      ZONE=${1-'tz'}
      TYPE=${2-'entries'}
      FILE=${3-''}
      # nightscout ns $NIGHTSCOUT_HOST $API_SECRET
      test -z ${ZONE} && echo "Missing first argument, ZONE, usually is set to tz" && exit 1
      test -z ${TYPE} && echo "Missing second argument, TYPE, one of: entries, treatments, devicestatus, profiles." && exit 1
      test ! -e ${FILE} && echo "Third argument, contents to upload, FILE, does not exist" && exit 1
      test ! -r ${FILE} && echo "Third argument, contents to upload, FILE, not readable." && exit 1
      openaps use ns shell lsgaps ${ZONE} ${TYPE} \
        |  openaps use ${ZONE} select --date dateString --current now --gaps - ${FILE}  | jq .
    ;;
    latest-entries-time)
      PREVIOUS_TIME=$(ns-get host $NIGHTSCOUT_HOST entries.json 'find[type][$eq]=sgv'  | jq .[0])
      test -z "${PREVIOUS_TIME}" && echo -n 0 || echo $PREVIOUS_TIME | jq .dateString
      exit 0
    ;;
    latest-treatment-time)
      PREVIOUS_TIME=$(ns-get host $NIGHTSCOUT_HOST treatments.json '?find[enteredBy]=/openaps:\/\//&count=1'  | jq .[0])
      test -z "${PREVIOUS_TIME}" && echo -n 0 || echo $PREVIOUS_TIME | jq -r .created_at
      exit 0
    # exec ns-get host $NIGHTSCOUT_HOST $*
    ;;
    format-recent-history-treatments)
      HISTORY=$1
      MODEL=$2
      LAST_TIME=$(nightscout ns $NIGHTSCOUT_HOST $API_SECRET latest-treatment-time)
      exec nightscout cull-latest-openaps-treatments $HISTORY $MODEL ${LAST_TIME}
      exit 0

    ;;
    upload-non-empty-type)
      TYPE=${1-entries.json}
      FILE=$2
      test $(cat $FILE | jq .[] | wc -l) -lt 1 && echo "Nothing to upload." >&2 && cat $FILE && exit 0
      exec ns-upload $NIGHTSCOUT_HOST $API_SECRET $TYPE $FILE
    ;;
    upload-non-empty-treatments)
      test $(cat $1 | jq .[] | wc -l) -lt 1 && echo "Nothing to upload." >&2 && cat $1 && exit 0
      exec ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json $1

    ;;
    upload)
      exec ns-upload $NIGHTSCOUT_HOST $API_SECRET $*
    ;;
    oref0_glucose)
      zone=${1-'tz'}
      shift
      params=$*
      params=${params-'count=10'}
      exec ns-get host $NIGHTSCOUT_HOST entries/sgv.json $params \
        | jq '[ .[] | .glucose = .sgv ]' \
        | openaps use $zone rezone --astimezone --date dateString -
    ;;
    oref0_glucose_without_zone)
      params=$*
      params=${params-'count=10'}
      exec ns-get host $NIGHTSCOUT_HOST entries/sgv.json $params \
        | jq '[ .[] | .glucose = .sgv ]' \
    ;;
    oref0_glucose_since)
      expr=$1
      zone=${2-'tz'}
      count=${3-1000}
      exec ns-get host $NIGHTSCOUT_HOST entries.json "find[date][\$gte]=$(date -d $expr +"%s%3N")&count=$count" \
        | jq '[ .[] | .glucose = .sgv ]' \
        | openaps use $zone rezone --astimezone --date dateString -
    ;;
    temp_targets)
      expr=${1--24hours}
      exec ns-get host $NIGHTSCOUT_HOST treatments.json "find[created_at][\$gte]=$(date -d $expr -Iminutes -u)&find[eventType]=Temporary+Target"
    ;;
    carb_history)
      expr=${1--24hours}
      exec ns-get host $NIGHTSCOUT_HOST treatments.json "find[created_at][\$gte]=$(date -d $expr -Iminutes -u)&find[carbs][\$exists]=true"
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
  API_SECRET=$(echo -n $1 | sha1sum | cut -d ' ' -f 1 | nonl)
  echo $API_SECRET
  ;;
autoconfigure-device-crud)
  NIGHTSCOUT_HOST=$1
  PLAIN_NS_SECRET=$2
  if [[ "${PLAIN_NS_SECRET,,}" =~ "token=" ]]; then
    API_SECRET=$2 # store token as API_SECRET
  else
    API_SECRET=$($self hash-api-secret $2)
  fi
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
  openaps device show ns --json | \
    jq '.extra.args |= sub("NIGHTSCOUT_HOST" ; "'$NIGHTSCOUT_HOST'")' \
    | jq '.extra.args |= sub("API_SECRET" ; "'$API_SECRET'")' \
    | openaps import
  ;;
cull-latest-openaps-treatments)
  INPUT=$1
  MODEL=$2
  LAST_TIME=$3
  mm-format-ns-treatments $INPUT $MODEL | jq '[ .[] | select(.created_at > "'$LAST_TIME'") ]'
  ;;
help|--help|-h)
  help_message
  exit 0
  ;;
*)
  test -n "$COMMAND" && exec $COMMAND $*
  ;;
esac
