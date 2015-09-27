#!/bin/bash


self=$0
NAME=$1
shift
PROGRAM="diyps-${NAME}"
COMMAND=$(which $PROGRAM | head -n 1)
if [ -n "$COMMAND" ] ; then
  exec $COMMAND "$*"
else
  cat <<EOF
  Usage:
$self <cmd>

Valid commands:
  diyps pebble
  diyps help - this message
EOF
fi


