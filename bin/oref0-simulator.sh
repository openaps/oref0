#!/bin/bash

# usage: $0

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

function init {
    #DIR=/tmp/oref0-simulator
    #if ! [[ -z "$1" ]]; then DIR=$1; fi
    echo Initializing $DIR
    mkdir -p $DIR || die "Couldn't mkdir -p $DIR"
    cd $DIR || die "Couldn't cd $DIR"
    rm *.json
    cp -r ~/src/oref0/examples/* ./
    #for file in pumphistory profile clock autosens glucose basal_profile carbhistory temp_basal; do
        #echo -n "${file}.json: "
        #if ! file_is_recent_and_min_size ${file}.json || ! jq -C -c . ${file}.json; then
            #echo $PWD/${file}.json is too old, does not exist, or is invalid: copying from ~/src/oref0/examples/
        #cp ~/src/oref0/examples/${file}.json ./
        #fi
    #done
    pwd && ls -la
    #echo
    exit 0
}

function main {

    # look up the currently active bg_target based on the current clock.json
    if grep target_bg profile.json; then
        target=$(jq .target_bg profile.json)
    else
        target=$((cat profile.json | jq -r '.bg_targets.targets[] | [.start, .min_bg] | @csv'; echo -n \"; cat clock.json | awk -F T '{print $2}') | sort | grep -B1 '\"$' | head -1 | awk -F , '{print $2}')
    fi
    if ! [ -z "$target" ]; then
        cat profile.json | jq ". | .min_bg=$target | .max_bg=$target" > profile.json.new
        echo setting target to $target
        #grep min_bg profile.json.new
        #grep target_bg profile.json.new
        if jq -e .dia profile.json.new >/dev/null; then
            mv profile.json.new profile.json
            cp profile.json settings/
            cp profile.json pumpprofile.json
            cp pumpprofile.json settings/
        fi
    fi

    jq .isfProfile profile.json > isf.json
    # only run autosens every "20m"
    if [[ -e autosens-override.json ]]; then
        cp autosens-override.json autosens.json
    elif egrep T[0-2][0-9]:[024][0-4]: clock.json; then
        oref0-detect-sensitivity glucose.json pumphistory.json isf.json basal_profile.json profile.json carbhistory.json retrospective > autosens.json
    fi
    oref0-calculate-iob pumphistory.json profile.json clock.json autosens.json > iob.json
    # calculate naive IOB without autosens
    oref0-calculate-iob pumphistory.json profile.json clock.json > naive_iob.json
    #cat naive_iob.json | jq -c .[0]
    oref0-meal pumphistory.json profile.json clock.json glucose.json basal_profile.json carbhistory.json > meal.json
    # calculate naive BGI and deviation without autosens
    oref0-determine-basal naive_iob.json temp_basal.json glucose.json profile.json --meal meal.json --microbolus --currentTime $(echo $(mydate -d $(cat clock.json | tr -d '"') +%s)000) > naive_suggested.json
    cat naive_suggested.json | jq -C -c '. | del(.predBGs) | del(.reason)'
    oref0-determine-basal iob.json temp_basal.json glucose.json profile.json --auto-sens autosens.json --meal meal.json --microbolus --currentTime $(echo $(mydate -d $(cat clock.json | tr -d '"') +%s)000) > suggested.json
    jq . -c suggested.json >> log.json
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
        # truncate to 400 pumphistory records
        # TODO: decide whether to save old pumphistory
        jq -s '[.[][]] | .[0:400]' newrecords.json pumphistory.json > pumphistory.json.new
        mv pumphistory.json.new pumphistory.json
    fi

    if jq -e .duration suggested.json > /dev/null; then
        # if suggested.json sets a new temp, put it into temp_basal.json and pumphistory.json
        jq '. | { rate: .rate, duration: .duration, temp: "absolute" }' suggested.json > temp_basal.json
        jq '. | [ { timestamp: .deliverAt, rate: .rate, temp: "absolute", _type: "TempBasal" } ]' suggested.json > newrecords.json
        jq '. | [ { timestamp: .deliverAt, "duration (min)": .duration, _type: "TempBasalDuration" } ]' suggested.json >> newrecords.json
        jq -s '[.[][]] | .[0:400]' newrecords.json pumphistory.json > pumphistory.json.new
        mv pumphistory.json.new pumphistory.json
    else
        # otherwise, advance the clock 5m on the currently running temp
        jq '. | .duration=.duration-5 | { rate: .rate, duration: .duration, temp: "absolute" }' temp_basal.json > temp_basal.json.new
        mv temp_basal.json.new temp_basal.json
    fi
    if ! [ -s temp_basal.json ]; then
        echo '{"rate": 0, "duration": 0, "temp": "absolute"}' > temp_basal.json
    fi
    #cat temp_basal.json | jq -c


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
    if ( jq -e .bg naive_suggested.json && jq -e .BGI naive_suggested.json && jq -e .deviation naive_suggested.json ) >/dev/null; then
        jq ".bg + .BGI + $deviation + $noiseformula |floor| [ { date: $(echo $(mydate -d $(cat clock.json | tr -d '"') +%s)000), glucose: ., sgv: ., dateString: \"$(mydate -d $(cat clock.json | tr -d '"') -Iseconds )\", device: \"fakecgm\" } ] " naive_suggested.json > newrecord.json
    else
        if [[ $deviation == *".deviation"* ]]; then
            adjustment=$noiseformula
        else
            adjustment="$deviation + $noiseformula"
        fi
        echo "Invalid suggested.json: updating glucose.json + $adjustment"
        jq '.[0].glucose + '"$adjustment"' |floor| [ { date: '$(echo $(mydate -d $(cat clock.json | tr -d '"')+5minutes +%s)000)', glucose: ., sgv: ., dateString: "'$(mydate -d $(cat clock.json | tr -d '"') -Iseconds )'", device: "fakecgm" } ] ' glucose.json | tee newrecord.json
    fi
    if jq -e '.[0].glucose < 39' newrecord.json > /dev/null; then
        echo "Glucose < 39 invalid"
        echo '[ { "date": '$(echo $(mydate -d $(cat clock.json | tr -d '"')  +%s)000)', "glucose": 39, "sgv": 39, "dateString": "'$(mydate -d $(cat clock.json | tr -d '"')+5minutes -Iseconds )'", "device": "fakecgm" } ] ' | tee newrecord.json
    fi
    # write a new glucose entry to glucose.json, and truncate it to 432 records (36 hours)
    jq -s '[.[][]] | .[0:432]' newrecord.json glucose.json > glucose.json.new
    mv glucose.json.new glucose.json
    # keep all glucose records for easy stats
    jq -s '[.[][]]' newrecord.json all-glucose.json > all-glucose.json.new
    mv all-glucose.json.new all-glucose.json

    # if there are any new carbs, add them to carbhistory.json
    addcarbs $carbs

    # advance the clock by 5m
    if jq -e .deliverAt suggested.json >/dev/null; then
        echo '"'$(mydate -d "$(cat suggested.json | jq .deliverAt | tr -d '"')+5 minutes" -Iseconds)'"' > clock.json
    else
        echo '"'$(mydate -d "$(cat clock.json | tr -d '"')+5minutes" -Iseconds)'"' > clock.json
    fi
}

function addcarbs {
    # if a carbs argument is provided, write the carb entry to carbhistory.json
    carbs=$1
    if ! [ -z "$carbs" ] && [ "$carbs" -gt 0 ]; then
        echo '[ { "carbs": '$carbs', "insulin": null, "created_at": "'$(mydate -d $(cat clock.json | tr -d '"')+5minutes -Iseconds )'", "enteredBy": "oref0-simulator" } ] ' | tee newrecord.json

        # write the new record to carbhistory.json, and truncate it to 100 records
        jq -s '[.[][]] | .[0:100]' newrecord.json carbhistory.json > carbhistory.json.new
        mv carbhistory.json.new carbhistory.json
    fi
}

function stats {
    echo Simulated:
    cat all-glucose.json | jq '.[] | select (.device=="fakecgm") | .sgv' | awk -f ~/src/oref0/bin/glucose-stats.awk
    #cat glucose.json | jq .[].sgv | awk -f ~/src/oref0/bin/glucose-stats.awk
    echo Actual:
    cat ns-entries.json | jq .[].sgv | awk -f ~/src/oref0/bin/glucose-stats.awk
}

if [[ $1 == *"init"* ]]; then
    DIR=/tmp/oref0-simulator
    if ! [[ -z "$2" ]]; then DIR=$2; fi
    init
else
    DIR=/tmp/oref0-simulator
    if ! [[ -z "$4" ]]; then DIR=$4; fi
    cd $DIR && ls glucose.json >/dev/null || init
    deviation=$1
    if [ -z "$1" ]; then deviation=0; fi
    noise=$2
    if [ -z "$2" ]; then noise=10; fi
    carbs=$3
    if [ -z "$3" ]; then carbs=0; fi
    echo Running oref-simulator with deviation $deviation, noise $noise, and carbs $carbs in dir $DIR
    main
    stats
fi

