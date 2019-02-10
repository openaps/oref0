#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

export GENERATE=false
export FILE=$1
export FILE2=$2
export COMMAND=$3

usage "$@" <<EOT
Usage: $self <target report> <age-check report>
EOT

if test ! -n "$FILE"; then
  print_usage
  exit 1
fi

if test ! -f $FILE; then
  echo "$FILE not found, invoking report"
  GENERATE=true
fi

if test -n "$(find settings/ -size -5c | grep $FILE)"; then
  echo "$FILE under 5 bytes, invoking report"
  GENERATE=true
fi

if test -n "$FILE2"; then
  if test -n "$(find settings/ -newer $FILE | grep $FILE2)"; then
    echo "$FILE older than $FILE2, invoking report"
    GENERATE=true
  fi
fi

if [ "$GENERATE" = true ]; then
  if test -n "$COMMAND"; then
    openaps $COMMAND
  else
    openaps report invoke $FILE
  fi
else
  echo "$FILE exists and is new, skipping invoke"
fi
