#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Normally runs from crontab.
EOT

date
cp -rf xdrip/glucose.json xdrip/last-glucose.json
curl --compressed -s --header "api-secret: "$API_SECRET http://192.168.44.1:17580/sgv.json?count=288 | json -e "this.glucose = this.sgv" > xdrip/glucose.json
if ! cmp --silent xdrip/glucose.json xdrip/last-glucose.json; then
    if cat xdrip/glucose.json | json -c "minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38" | grep -q glucose; then
        cp -up xdrip/glucose.json monitor/glucose.json
        echo "Updating glucose.json from xDrip+"
    else
        echo No recent glucose data downloaded from xDrip.
        diff xdrip/glucose.json xdrip/last-glucose.json
    fi
fi
