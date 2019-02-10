#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self <glucose.json> <sample-interval> <max-wait>
Sleep until a new glucose value is expected from the CGM. Takes a log of recent
glucose samples, the sample interval, and the maximum amount of time to wait.
EOT


GLUCOSE=$1

OLD=${2-5}
MAX_WAIT=${3-1}
TIME_SINCE=$(oref0-dex-time-since $GLUCOSE)

if (( $(bc <<< "$TIME_SINCE >= $OLD") )); then
  echo "CGM Data $TIME_SINCE mins ago is old (>=$OLD), not waiting"
else
  WAIT_MINS=$(bc <<< "$OLD - $TIME_SINCE")
  if (( $(bc <<< "$WAIT_MINS > 6") )); then
    echo "Clock mismatch ($WAIT_MINS > 6); not waiting"
  elif (( $(bc <<< "$WAIT_MINS >= $MAX_WAIT") )); then
    echo "CGM Data $TIME_SINCE mins ago is fresh (< $OLD), $WAIT_MINS mins > max wait ($MAX_WAIT mins) waiting for next attempt"
    exit 1
  else
    echo "CGM Data $TIME_SINCE mins ago is fresh (< $OLD), waiting $WAIT_MINS mins for new data"
    sleep ${WAIT_MINS}m
    echo "finished waiting, let's get some CGM Data"
  fi
fi

