#!/bin/bash

GLUCOSE=$1

OLD=${2-5}
TIME_SINCE=$(oref0-dex-time-since $GLUCOSE)

if (( $(bc <<< "$TIME_SINCE >= $OLD") )); then
  echo "CGM Data $TIME_SINCE mins ago is old (>=$OLD)"
  exit 1
else
  echo "CGM Data $TIME_SINCE mins ago is fresh (< $OLD)"
  exit 0
fi

