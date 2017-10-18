#!/bin/bash

cat "${1:-/dev/stdin}" \
    | tee /tmp/temptarget.json \
    && jq -s '[.[0]] + .[1]' /tmp/temptarget.json settings/local-temptargets.json \
    | tee settings/local-temptargets.json.new \
    && mv settings/local-temptargets.json.new settings/local-temptargets.json
