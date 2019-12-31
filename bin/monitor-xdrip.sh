#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Normally runs from crontab.
EOT

date
cp -rf xdrip/glucose.json xdrip/last-glucose.json
curl --compressed -s http://localhost:5000/api/v1/entries?count=288 | jq '[ .[] | .glucose = .sgv ]' > xdrip/glucose.json
if ! cmp --silent xdrip/glucose.json xdrip/last-glucose.json; then
    if cat xdrip/glucose.json
    	|  jq \
	        --arg AT_LATEST   "`date -u +'%Y-%m-%dT%H:%M:%S.000Z' --date '5 minutes'`"\
	        --arg AT_EARLIEST "`date -u +'%Y-%m-%dT%H:%M:%S.000Z' --date '-10 minutes'`"\
	        '[.[] | (select (.dateString >= $AT_EARLIEST)) | (select (.dateString <= $AT_LATEST)) | (select (.glucose > 38))]'
    	| grep -q glucose; then
        cp -up xdrip/glucose.json monitor/glucose.json
    else
        echo No recent glucose data downloaded from xDrip.
        diff xdrip/glucose.json xdrip/last-glucose.json
    fi
fi
