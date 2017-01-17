#!/bin/bash

set -u

die() {
    echo "$@"
    exit 1
}

#ls -lart monitor/
# Delete suggested.json
rm -rf enact/suggested.json
ls enact/suggested.json 2>/dev/null && die "enact/suggested.json present"
openaps get-ns-bg
#killall -g openaps
#openaps wait-for-silence
openaps use pump model 2>/dev/null || openaps mmtune
# Refresh reservoir.json # Refresh pumphistory.json
openaps gather || die "Couldn't run openaps gather"
cp monitor/reservoir.json monitor/lastreservoir.json
cat monitor/reservoir.json
head monitor/pumphistory.json
 # Make sure pumphistory.json is newer than reservoir.json
find monitor/ -ls -newer monitor/reservoir.json | grep monitor/pumphistory.json || die "pumphistory.json is not newer than reservoir.json"
# Run determine-basal  TODO: Make this a report
oref0-determine-basal monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json settings/autosens.json monitor/meal.json --microbolus > enact/suggested.json || die "Could not create suggested.json"
# Enact the recommended zero temp, if any
openaps invoke enact/enacted.json || die "Couldn't set zero temp"
#TODO: check these, as well as duration and timestamp, with json tools
cat enact/enacted.json | json -0
# Read the currently running temp and TODO: verify it matches the recommended
openaps invoke monitor/temp_basal.json || die "Couldn't refresh temp_basal.json"
grep '"rate": 0.0,' monitor/temp_basal.json || die "Temp basal not zero"
# Read the pump reservoir volume and verify it is within 0.1U of the expected volume
openaps invoke monitor/reservoir.json || openaps invoke monitor/reservoir.json || die "Couldn't re-refresh reservoir.json" 
diff -u monitor/lastreservoir.json monitor/reservoir.json && echo -n "Reservoir level unchanged at " && cat monitor/reservoir.json && echo || die "Reservoir level changed"
# Read the pump status and verify it is not bolusing
openaps invoke monitor/status.json || die "Couldn't refresh status.json"
grep '"status": "normal"' monitor/status.json && grep '"bolusing": false' monitor/status.json && grep '"suspended": false' monitor/status.json || die "Pump status error"
# TODO: Verify that the suggested.json is less than 5 minutes old, and that the current time is prior to the timestamp by which the microbolus needs to be sent
# Administer the supermicrobolus
grep '"units":' enact/suggested.json || die "suggested.json doesn't have a bolus to set"
echo 'Time to SMB'
#TODO: Make this a report
openaps use pump bolus enact/suggested.json > enact/bolused.json
cat enact/bolused.json | json -0
# Delete suggested.json
rm -rf enact/suggested.json
