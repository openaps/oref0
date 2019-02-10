#!/bin/bash

oref0-calculate-iob pumphistory.json profile.json clock.json autosens.json > iob.json
oref0-meal pumphistory.json profile.json clock.json glucose.json basal_profile.json carbhistory.json > meal.json
oref0-determine-basal iob.json temp_basal.json glucose.json profile.json --auto-sens autosens.json --meal meal.json --microbolus --currentTime 1527924300000 > suggested.json
cat suggested.json | jq -C -c '. | del(.predBGs) | del(.reason)'
cat suggested.json | jq -C -c .reason
cat suggested.json | jq -C -c .predBGs
