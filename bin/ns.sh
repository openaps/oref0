#!/bin/bash


self=$(basename $0)
NAME=${1-help}
shift
PROGRAM="ns-${NAME}"
COMMAND=$(which $PROGRAM | head -n 1)

function help_message ( ) {
  cat <<EOF
  Usage:
$self <cmd>

EOF
}

case $NAME in
latest-openaps-treatment)
  ns-get treatments.json'?count=5' $* | json -c "this.enteredBy && this.enteredBy.indexOf('openaps://') === 0" | json 0
  ;;
cull-latest-openaps-treatments)
  INPUT=$1
  MODEL=$2
  LAST_TIME=$3
  mm-format-ns-treatments $INPUT $MODEL |  json -c "this.created_at > '$LAST_TIME'"
  ;;
help)
  help_message
  ;;
*)
  test -n "$COMMAND" && exec $COMMAND $*
  ;;
esac


