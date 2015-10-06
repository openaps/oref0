#!/bin/bash


self=$0
NAME=${1-help}
shift
PROGRAM="oref0-${NAME}"
COMMAND=$(which $PROGRAM | head -n 1)

function help_message ( ) {
  cat <<EOF
  Usage:
$self <cmd>

Valid commands:
  oref0 pebble
  oref0 get-profile
  oref0 calculate-iob
  oref0 determine-basal
  oref0 help - this message
EOF
}

case $NAME in
env)
  echo PATH=$PATH
  env
  exit
  ;;
help)
  help_message
  ;;
*)
  test -n "$COMMAND" && exec $COMMAND $*
  ;;
esac


