#!/bin/bash


self=$0
NAME=$1
shift
PROGRAM="diyps-${NAME}"
COMMAND=$(which $PROGRAM | head -n 1)

function help_message ( ) {
  cat <<EOF
  Usage:
$self <cmd>

Valid commands:
  diyps pebble
  diyps calculate-iob
  diyps determine-basal
  diyps help - this message
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


