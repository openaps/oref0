#!/bin/bash

if [[ ! -z "$2" ]]; then
    input=$(oref0-set-local-temptarget $@)
elif [[ ! -z "$1" ]]; then
    input=$(cat $1)
else
    input=$(cat /dev/stdin)
fi
#cat "${1:-/dev/stdin}" \
echo $input \
    | tee /tmp/temptarget.json \
    && jq -s '[.[0]] + .[1]' /tmp/temptarget.json settings/local-temptargets.json \
    | tee settings/local-temptargets.json.new \
    && mv settings/local-temptargets.json.new settings/local-temptargets.json
