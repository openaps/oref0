#!/bin/bash

export GENERATE=false
export FILE=$1
export FILE2=$2
export COMMAND=$3

if test ! -n "$FILE"; then
  echo "Usage: oref0-crun <target report> <age-check report>"
  exit
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