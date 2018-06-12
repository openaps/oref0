#!/bin/bash

# usage: $0 

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

if [[ $1 == *"init"* ]]; then
    mkdir -p /tmp/oref0-simulator
    cd /tmp/oref0-simulator
    for file in pumphistory profile clock autosens glucose basal_profile carbhistory temp_basal; do
        #echo -n "${file}.json: "
        #if ! file_is_recent_and_min_size ${file}.json || ! jq -C -c . ${file}.json; then
            #echo $PWD/${file}.json is too old, does not exist, or is invalid: copying from ~/src/oref0/examples/
        cp ~/src/oref0/examples/${file}.json ./
        #fi
    done
    ls -la
    #echo
    exit 0
else 
    deviation=$1
    noise=$2
fi

jq .isfProfile profile.json > isf.json
# only run autosens every "20m"
if egrep T[0-2][0-9]:[024]0: clock.json; then
    oref0-detect-sensitivity glucose.json pumphistory.json isf.json basal_profile.json profile.json carbhistory.json > autosens.json
fi
oref0-calculate-iob pumphistory.json profile.json clock.json autosens.json > iob.json
# calculate naive IOB without autosens
oref0-calculate-iob pumphistory.json profile.json clock.json > naive_iob.json
oref0-meal pumphistory.json profile.json clock.json glucose.json basal_profile.json carbhistory.json > meal.json
# calculate naive BGI and deviation without autosens
oref0-determine-basal naive_iob.json temp_basal.json glucose.json profile.json meal.json --microbolus --currentTime $(echo $(date -d $(cat clock.json | tr -d '"') +%s)000) > naive_suggested.json
cat naive_suggested.json | jq -C -c '. | del(.predBGs) | del(.reason)'
oref0-determine-basal iob.json temp_basal.json glucose.json profile.json autosens.json meal.json --microbolus --currentTime $(echo $(date -d $(cat clock.json | tr -d '"') +%s)000) > suggested.json
cat suggested.json | jq -C -c '. | del(.predBGs) | del(.reason)'
cat suggested.json | jq -C -c .reason
#cat suggested.json | jq -C -c .predBGs
echo -n "ZT:  " && jq -C -c .predBGs.ZT suggested.json
echo -n "IOB: " && jq -C -c .predBGs.IOB suggested.json
echo -n "UAM: " && jq -C -c .predBGs.UAM suggested.json
echo -n "COB: " && jq -C -c .predBGs.COB suggested.json

if jq -e .units suggested.json > /dev/null; then
    # if suggested.json delivers an SMB, put it into pumphistory.json
    jq '. | [ { timestamp: .deliverAt, amount: .units, duration: 0, _type: "Bolus" } ]' suggested.json > newrecords.json
    jq -s '[.[][]]' newrecords.json pumphistory.json > pumphistory.json.new
    mv pumphistory.json.new pumphistory.json
fi

if jq -e .duration suggested.json > /dev/null; then
    # if suggested.json sets a new temp, put it into temp_basal.json and pumphistory.json
    jq '. | { rate: .rate, duration: .duration, temp: "absolute" }' suggested.json > temp_basal.json
    jq '. | [ { timestamp: .deliverAt, rate: .rate, temp: "absolute", _type: "TempBasal" } ]' suggested.json > newrecords.json
    jq '. | [ { timestamp: .deliverAt, "duration (min)": .duration, _type: "TempBasalDuration" } ]' suggested.json >> newrecords.json
    jq -s '[.[][]]' newrecords.json pumphistory.json > pumphistory.json.new
    mv pumphistory.json.new pumphistory.json
else
    # otherwise, advance the clock 5m on the currently running temp
    jq '. | .duration=.duration-5 | { rate: .rate, duration: .duration, temp: "absolute" }' temp_basal.json > temp_basal.json.new
    mv temp_basal.json.new temp_basal.json
fi


if [ -z $deviation ]; then
    # if deviation is unspecified, randomly decay the current deviation
    deviation=".deviation / 6 * ($RANDOM/32767)"
    echo -n "Deviation unspecified, using $deviation"
else
    echo -n Using deviation of $deviation
fi
if [ -z $noise ]; then
    # this adds a random +/- $noise mg/dL every run (the 0.5 is to work with |floor)
    noise=3
fi
noiseformula="2*$noise*$RANDOM/32767 - $noise + 0.5"
echo " and noise of +/- $noise ($noiseformula)"
# write a new glucose entry to glucose.json using the 
if ( jq -e .bg naive_suggested.json && jq -e .BGI naive_suggested.json && jq -e .deviation naive_suggested.json ) >/dev/null; then
    jq ".bg + .BGI + $deviation + $noiseformula |floor| [ { date: $(echo $(date -d $(cat clock.json | tr -d '"') +%s)000), glucose: ., sgv: ., dateString: \"$(date -d $(cat clock.json | tr -d '"') -Iseconds )\", device: \"fakecgm\" } ] " naive_suggested.json > newrecord.json
else
    echo "Invalid suggested.json: updating glucose.json +/- $noise"
    if [[ $deviation == *".deviation"* ]]; then
        adjustment=$noiseformula
    else
        adjustment="$deviation + $noiseformula"
    fi
    jq ".[0].glucose + $adjustment |floor| [ { date: $(echo $(date -d $(cat clock.json | tr -d '"') +%s)000), glucose: ., sgv: ., dateString: \"$(date -d $(cat clock.json | tr -d '"') -Iseconds )\", device: \"fakecgm\" } ] " glucose.json | tee newrecord.json
fi
if jq -e '.[0].glucose < 39' newrecord.json; then
    echo "Glucose < 39 invalid"
else
    jq -s '[.[][]]' newrecord.json glucose.json > glucose.json.new
    mv glucose.json.new glucose.json
fi

# advance the clock by 5m
if jq -e .deliverAt suggested.json >/dev/null; then
    echo '"'$(date -d "$(cat suggested.json | jq .deliverAt | tr -d '"')+5 minutes" -Iseconds)'"' > clock.json
fi

#cd -
