#!/bin/bash


self=$(basename $0)
NAME=${1-help}
shift
PROGRAM="oref0-${NAME}"
COMMAND=$(which $PROGRAM | head -n 1)

function help_message ( ) {
  cat <<EOF
  Usage:
$self <cmd>

 ______   ______   ______  ______ 0
/ |  | \ | |  | \ | |     | |      
| |  | | | |__| | | |---- | |----  
\_|__|_/ |_|  \_\ |_|____ |_|      

Valid commands:
  oref0 env - print information about environment.
  oref0 pebble
  oref0 ifttt-notify
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


