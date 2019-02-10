#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self -|<filename>|<target> <duration> [starttime]

Set a temporary target, by formatting it as JSON and storing it in
settings/local-temptargets.json where the pump loop will find it on its next
iteration.

If no arguments are given, expects JSON on stdin. If one argument is given,
it's the name of a file containing JSON describing a temporary target. If two
or more arguments, they are a target, duration, and optional start time (as
with oref0-set-local-temptarget.js).
EOT


if [[ ! -z "$2" ]]; then
    # If two or more arguments, runs oref0-set-local-temptarget.js forwarding
    # all its arguments, and input is the output of that.
    input=$(oref0-set-local-temptarget $@)
elif [[ ! -z "$1" ]]; then
    # If exactly one argument, it's a filename
    input=$(cat $1)
else
    # If no arguments, act like a filter
    input=$(cat /dev/stdin)
fi
#cat "${1:-/dev/stdin}" \
echo $input \
    | tee /tmp/temptarget.json \
    && jq -s '[.[0]] + .[1]' /tmp/temptarget.json settings/local-temptargets.json \
    | tee settings/local-temptargets.json.new \
    && mv settings/local-temptargets.json.new settings/local-temptargets.json
