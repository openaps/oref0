#!/bin/bash
# echo Starting ns-loop at $(date): && openaps get-ns-bg; sensors -u 2>/dev/null | awk '$NF > 85' | grep input || ( openaps ns-temptargets && echo -n Refreshed temptargets && openaps ns-meal-carbs && echo \\\" and meal-carbs\\\" && openaps upload )
# echo Starting ns-loop at $(date): && openaps get-ns-bg; openaps ns-temptargets && echo -n Refreshed temptargets && openaps ns-meal-carbs && echo \\\" and meal-carbs\\\" && openaps battery-status; cat monitor/edison-battery.json; echo; openaps upload

# main ns-loop
main() {
    echo
    echo Starting oref0-ns-loop at $(date):
    if glucose_fresh; then
        echo Glucose file is fresh
        cat cgm/ns-glucose.json | jq -c -C '.[0] | { glucose: .glucose, dateString: .dateString }'
    else
        get_ns_bg
    fi
    overtemp && exit 1
    if highload && completed_recently; then
        echo Load high at $(date): waiting up to 5m to continue
        exit 2
    fi

    ns_temptargets || die "ns_temptargets failed"
    ns_meal_carbs || die ", but ns_meal_carbs failed"
    battery_status
    upload
    # if glucose is stale, refresh before running autosens
    if ! glucose_fresh; then get_ns_bg; fi
    autosens
    # check one last time to see if glucose got stale while running everything else
    if ! glucose_fresh; then get_ns_bg; fi
    touch /tmp/ns-loop-completed
    echo Completed oref0-ns-loop at $(date)
}

function overtemp {
    # check for CPU temperature above 85°C
    sensors -u 2>/dev/null | awk '$NF > 85' | grep input \
    && echo Edison is too hot: waiting for it to cool down at $(date)\
    && echo Please ensure rig is properly ventilated
}

function highload {
    # check whether system load average is high
    uptime | awk '$NF > 2' | grep load
}


#openaps get-ns-glucose && cat cgm/ns-glucose.json | json -c \\\"minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38\\\" | grep -q glucose && cp -pu cgm/ns-glucose.json cgm/glucose.json; cp -pu cgm/glucose.json monitor/glucose.json
function get_ns_bg {
    #openaps get-ns-glucose > /dev/null
    # update 24h glucose file if it's 55m old or too small to calculate COB
    if ! find cgm/ -mmin -54 | egrep -q cgm/ns-glucose-24h.json \
        || ! grep -c glucose cgm/ns-glucose-24h.json | jq -e '. > 36' >/dev/null; then
        nightscout ns $NIGHTSCOUT_HOST $API_SECRET oref0_glucose_since -24hours > cgm/ns-glucose-24h.json
    fi
    nightscout ns $NIGHTSCOUT_HOST $API_SECRET oref0_glucose_since -1hour > cgm/ns-glucose-1h.json
    jq -s '.[0] + .[1]|unique|sort_by(.date)|reverse' cgm/ns-glucose-24h.json cgm/ns-glucose-1h.json > cgm/ns-glucose.json
    # if ns-glucose.json data is <10m old, no more than 5m in the future, and valid (>38),
    # copy cgm/ns-glucose.json over to cgm/glucose.json if it's newer
    valid_glucose=$(find_valid_ns_glucose)
    if echo $valid_glucose | grep -q glucose; then
        echo Found recent valid BG:
        echo $valid_glucose | jq -c -C '.[0] | { glucose: .glucose, dateString: .dateString }'
        cp -pu cgm/ns-glucose.json cgm/glucose.json
    else
        echo No recent valid BG found. Most recent:
        cat cgm/ns-glucose.json | jq -c -C '.[0] | { glucose: .glucose, dateString: .dateString }'
    fi

    # copy cgm/glucose.json over to monitor/glucose.json if it's newer
    cp -pu cgm/glucose.json monitor/glucose.json
}

function completed_recently {
    find /tmp/ -mmin -5 | egrep -q "ns-loop-completed"
}

function glucose_fresh {
    # check whether ns-glucose.json is less than 5m old
    touch -d "$(date -R -d @$(jq .[0].date/1000 cgm/ns-glucose.json))" cgm/ns-glucose.json
    find cgm -mmin -5 | egrep -q "ns-glucose.json"
}

function find_valid_ns_glucose {
    # TODO: use jq for this if possible
    cat cgm/ns-glucose.json | json -c "minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38"
}

function ns_temptargets {
    #openaps report invoke settings/temptargets.json settings/profile.json >/dev/null
    nightscout ns $NIGHTSCOUT_HOST $API_SECRET temp_targets > settings/ns-temptargets.json
    # TODO: merge local-temptargets.json with ns-temptargets.json
    #openaps report invoke settings/ns-temptargets.json settings/profile.json
    echo -n "Refreshed NS temptargets: "
    cat settings/ns-temptargets.json | jq -c -C '.[0] | { target: .targetBottom, duration: .duration, start: .created_at }'
    # delete any local-temptarget files last modified more than 24h ago
    find settings/local-temptarget* -mmin +1440 -exec rm {} \;
    echo -n "Merging local temptargets: "
    cat settings/local-temptargets.json | jq -c -C '.[0] | { target: .targetBottom, duration: .duration, start: .created_at }'
    jq -s '.[0] + .[1]|unique|sort_by(.created_at)|reverse' settings/ns-temptargets.json settings/local-temptargets.json > settings/temptargets.json
    echo -n "Temptargets merged: "
    cat settings/temptargets.json | jq -c -C '.[0] | { target: .targetBottom, duration: .duration, start: .created_at }'
    oref0-get-profile settings/settings.json settings/bg_targets.json settings/insulin_sensitivities.json settings/basal_profile.json preferences.json settings/carb_ratios.json settings/temptargets.json --model=settings/model.json --autotune settings/autotune.json | jq . > settings/profile.json.new || die "Couldn't refresh profile"
    if cat settings/profile.json.new | jq . | grep -q basal; then
        mv settings/profile.json.new settings/profile.json
    else
        die "Invalid profile.json.new after refresh"
    fi
}

# openaps report invoke monitor/carbhistory.json; oref0-meal monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new; grep -q COB monitor/meal.json.new && mv monitor/meal.json.new monitor/meal.json; exit 0
function ns_meal_carbs {
    #openaps report invoke monitor/carbhistory.json >/dev/null
    nightscout ns $NIGHTSCOUT_HOST $API_SECRET carb_history > monitor/carbhistory.json
    oref0-meal monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new
    grep -q COB monitor/meal.json.new && mv monitor/meal.json.new monitor/meal.json
    echo -n "Refreshed carbhistory; COB: "
    grep COB monitor/meal.json | jq .mealCOB
}

#sudo ~/src/EdisonVoltage/voltage json batteryVoltage battery > monitor/edison-battery.json
function battery_status {
    if [ -e ~/src/EdisonVoltage/voltage ]; then
        sudo ~/src/EdisonVoltage/voltage json batteryVoltage battery | tee monitor/edison-battery.json | jq -C -c .
    fi
}

# echo -n Upload && ( openaps upload-ns-status; openaps upload-pumphistory-entries; openaps upload-recent-treatments ) 2>/dev/null >/dev/null && echo ed
function upload {
    upload_ns_status
    upload_recent_treatments || die "; NS treatments upload failed"
}

# grep -q iob monitor/iob.json && find enact/ -mmin -5 -size +5c | grep -q suggested.json && openaps format-ns-status && grep -q iob upload/ns-status.json && ns-upload $NIGHTSCOUT_HOST $API_SECRET devicestatus.json upload/ns-status.json
function upload_ns_status {
    #echo Uploading devicestatus
    grep -q iob monitor/iob.json || die "IOB not found"
    if ! find enact/ -mmin -5 -size +5c | grep -q suggested.json; then
        echo -n "No recent suggested.json found; last updated "
        ls -la enact/suggested.json | awk '{print $6,$7,$8}'
        return 1
    fi
    format_ns_status && grep -q iob upload/ns-status.json || die "Couldn't generate ns-status.json"
    ns-upload $NIGHTSCOUT_HOST $API_SECRET devicestatus.json upload/ns-status.json | jq -C -c '.[0].openaps.suggested | {BG: .bg, IOB: .IOB, rate: .rate, duration: .duration, units: .units}' || die "Couldn't upload devicestatus to NS"
}

#ns-status monitor/clock-zoned.json monitor/iob.json enact/suggested.json enact/enacted.json monitor/battery.json monitor/reservoir.json monitor/status.json > upload/ns-status.json
# ns-status monitor/clock-zoned.json monitor/iob.json enact/suggested.json enact/enacted.json monitor/battery.json monitor/reservoir.json monitor/status.json --uploader monitor/edison-battery.json > upload/ns-status.json
function format_ns_status {
    if [ -e monitor/edison-battery.json ]; then
        ns-status monitor/clock-zoned.json monitor/iob.json enact/suggested.json enact/enacted.json monitor/battery.json monitor/reservoir.json monitor/status.json --uploader monitor/edison-battery.json > upload/ns-status.json
    else
        ns-status monitor/clock-zoned.json monitor/iob.json enact/suggested.json enact/enacted.json monitor/battery.json monitor/reservoir.json monitor/status.json > upload/ns-status.json
    fi
}

#openaps format-latest-nightscout-treatments && test $(json -f upload/latest-treatments.json -a created_at eventType | wc -l ) -gt 0 && (ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json upload/latest-treatments.json ) || echo \\\"No recent treatments to upload\\\"
function upload_recent_treatments {
    #echo Uploading treatments
    format_latest_nightscout_treatments || die "Couldn't format latest NS treatments"
    if test $(json -f upload/latest-treatments.json -a created_at eventType | wc -l ) -gt 0; then
        ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json upload/latest-treatments.json | jq -C -c . || die "Couldn't upload latest treatments to NS"
    else
        echo "No new treatments to upload"
    fi
}

#nightscout cull-latest-openaps-treatments monitor/pumphistory-zoned.json settings/model.json $(openaps latest-ns-treatment-time) > upload/latest-treatments.json
function format_latest_nightscout_treatments {
    nightscout cull-latest-openaps-treatments monitor/pumphistory-zoned.json settings/model.json $(openaps latest-ns-treatment-time) > upload/latest-treatments.json
}

# find settings/ -newer settings/autosens.json | grep -q pumphistory-24h-zoned.json || find settings/ -size -5c | grep -q autosens.json || ! find settings/ | grep -q autosens || ! find settings/autosens.json
# openaps use detect-sensitivity shell monitor/glucose.json settings/pumphistory-24h-zoned.json settings/insulin_sensitivities.json settings/basal_profile.json settings/profile.json monitor/carbhistory.json settings/temptargets.json
function autosens {
    # only run autosens if pumphistory-24h is newer than autosens
    if find settings/ -newer settings/autosens.json | grep -q pumphistory-24h-zoned.json \
        || find settings/ -size -5c | grep -q autosens.json \
        || ! find settings/ | grep -q autosens \
        || ! find settings/autosens.json; then
        if oref0-detect-sensitivity monitor/glucose.json settings/pumphistory-24h-zoned.json settings/insulin_sensitivities.json settings/basal_profile.json settings/profile.json monitor/carbhistory.json settings/temptargets.json > settings/autosens.json.new && cat settings/autosens.json.new | jq .ratio | grep [0-9]; then
            mv settings/autosens.json.new settings/autosens.json
            echo -n Autosens refreshed
        else
            echo -n Failed to refresh autosens: using old autosens.json
        fi
    else
        echo -n No need to refresh autosens yet
    fi
    cat settings/autosens.json | jq . -C -c
}

die() {
    echo "$@"
    exit 1
}

main "$@"
