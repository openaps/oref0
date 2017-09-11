#!/bin/bash

date
cp -rf xdrip/glucose.json xdrip/last-glucose.json
curl --compressed -s http://localhost:5000/api/v1/entries?count=288 | json -e "this.glucose = this.sgv" > xdrip/glucose.json
if ! cmp --silent xdrip/glucose.json xdrip/last-glucose.json; then
    if cat xdrip/glucose.json | json -c "minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38" | grep -q glucose; then
        cp -up xdrip/glucose.json monitor/glucose.json
    else
        echo No recent glucose data downloaded from xDrip.
        diff xdrip/glucose.json xdrip/last-glucose.json
    fi
fi
