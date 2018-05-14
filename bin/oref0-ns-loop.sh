#!/bin/bash
# echo Starting ns-loop at $(date): && openaps get-ns-bg; sensors -u 2>/dev/null | awk '$NF > 85' | grep input || ( openaps ns-temptargets && echo -n Refreshed temptargets && openaps ns-meal-carbs && echo \\\" and meal-carbs\\\" && openaps upload )
# echo Starting ns-loop at $(date): && openaps get-ns-bg; openaps ns-temptargets && echo -n Refreshed temptargets && openaps ns-meal-carbs && echo \\\" and meal-carbs\\\" && openaps battery-status; cat monitor/edison-battery.json; echo; openaps upload

# main ns-loop
main() {
    echo
    echo Starting oref0-ns-loop at $(date):
    if grep "MDT cgm" openaps.ini 2>&1 >/dev/null; then
        check_mdt_upload
    else
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
    fi

    pushover_snooze
    ns_temptargets || die "ns_temptargets failed"
    ns_meal_carbs || die ", but ns_meal_carbs failed"
    battery_status
    upload
    touch /tmp/ns-loop-completed
    echo Completed oref0-ns-loop at $(date)
}

function pushover_snooze {
    URL=$NIGHTSCOUT_HOST/api/v1/devicestatus.json?count=100
    if snooze=$(curl -s $URL | jq '.[] | select(.snooze=="carbsReq") | select(.date>'$(date +%s -d "10 minutes ago")')' | jq -s .[0].date | tr -d '"'); then
        #echo $snooze
        #echo date -Is -d @$snooze; echo
        touch -d $(date -Is -d @$snooze) monitor/pushover-sent
        ls -la monitor/pushover-sent
    fi
}

function overtemp {
    # check for CPU temperature above 85°C
    sensors -u 2>/dev/null | awk '$NF > 85' | grep input \
    && echo Edison is too hot: waiting for it to cool down at $(date)\
    && echo Please ensure rig is properly ventilated
}

function highload {
    # check whether system load average is high
    uptime | tr -d ',' | awk "\$(NF-2) > 4" | grep load
}


function get_ns_bg {
    #openaps get-ns-glucose > /dev/null
    # update 24h glucose file if it's 55m old or too small to calculate COB
    if ! find cgm/ -mmin -54 | egrep -q cgm/ns-glucose-24h.json \
        || ! grep -c glucose cgm/ns-glucose-24h.json | jq -e '. > 36' >/dev/null; then
        nightscout ns $NIGHTSCOUT_HOST $API_SECRET oref0_glucose_since -24hours > cgm/ns-glucose-24h.json
    fi
    nightscout ns $NIGHTSCOUT_HOST $API_SECRET oref0_glucose_since -1hour > cgm/ns-glucose-1h.json
    jq -s '.[0] + .[1]|unique|sort_by(.date)|reverse' cgm/ns-glucose-24h.json cgm/ns-glucose-1h.json > cgm/ns-glucose.json
    glucose_fresh # update timestamp on cgm/ns-glucose.json
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
    nightscout ns $NIGHTSCOUT_HOST $API_SECRET temp_targets > settings/ns-temptargets.json.new
    cat settings/ns-temptargets.json.new | jq .[0].duration | egrep -q [0-9] && mv settings/ns-temptargets.json.new settings/ns-temptargets.json
    # TODO: merge local-temptargets.json with ns-temptargets.json
    #openaps report invoke settings/ns-temptargets.json settings/profile.json
    echo -n "Latest NS temptargets: "
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
    nightscout ns $NIGHTSCOUT_HOST $API_SECRET carb_history > monitor/carbhistory.json.new
    cat monitor/carbhistory.json.new | jq .[0].carbs | egrep -q [0-9] && mv monitor/carbhistory.json.new monitor/carbhistory.json
    oref0-meal monitor/pumphistory-24h-zoned.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new
    grep -q COB monitor/meal.json.new && mv monitor/meal.json.new monitor/meal.json
    echo -n "Refreshed carbhistory; COB: "
    grep COB monitor/meal.json | jq .mealCOB
}

#sudo ~/src/EdisonVoltage/voltage json batteryVoltage battery > monitor/edison-battery.json
function battery_status {
    if [ -e ~/src/EdisonVoltage/voltage ]; then
        sudo ~/src/EdisonVoltage/voltage json batteryVoltage battery | tee monitor/edison-battery.json | jq -C -c .
    elif [ -e /root/src/openaps-menu/scripts/getvoltage.sh ]; then
        sudo /root/src/openaps-menu/scripts/getvoltage.sh | tee monitor/edison-battery.json | jq -C -c .
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
    # set the timestamp on enact/suggested.json to match the deliverAt time
    touch -d $(cat enact/suggested.json | jq .deliverAt | sed 's/"//g') enact/suggested.json
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
    if [ -s monitor/edison-battery.json ]; then
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
    latest_ns_treatment_time=$(openaps latest-ns-treatment-time)
    historyfile=monitor/pumphistory-24h-zoned.json
    # TODO: remove this hack once we actually start parsing pump time change events
    if [[ $latest_ns_treatment_time > $(date -Is) ]]; then
        echo "Latest NS treatment time $latest_ns_treatment_time is 'in the future' / from a timezone east of here."
        latest_ns_treatment_time=$(date -Is -d "1 hour ago")
        echo "Uploading the last 10 treatments since $latest_ns_treatment_time"
        jq .[0:9] monitor/pumphistory-24h-zoned.json > upload/recent-pumphistory.json
        historyfile=upload/recent-pumphistory.json
    fi
        nightscout cull-latest-openaps-treatments $historyfile settings/model.json $latest_ns_treatment_time > upload/latest-treatments.json
}

function check_mdt_upload {
    if [ -f /tmp/mdt_cgm_uploaded ]; then
        if [ $(date -d $(jq .[0].dateString nightscout/glucose.json | tr -d '"') +%s) -gt $(date -r /tmp/mdt_cgm_uploaded +%s) ];then
            echo Found new MDT CGM data to upload:
            echo "BG: $(jq .[0].glucose nightscout/glucose.json)" "at $(jq .[0].dateString nightscout/glucose.json | tr -d '"')"
            mdt_upload_bg
        else
            echo No new MDT CGM data to upload
        fi
    elif [ -f nightscout/glucose.json ]; then
        mdt_upload_bg
    else
        echo No cgm data available
    fi
}

function mdt_upload_bg {
    echo Formating recent-missing-entries
    openaps report invoke nightscout/recent-missing-entries.json 2>&1 >/dev/null
    if grep "dateString" nightscout/recent-missing-entries.json 2>&1 >/dev/null; then
        echo "$(jq '. | length' nightscout/recent-missing-entries.json) missing entires found, uploading"
        openaps report invoke nightscout/uploaded-entries.json 2>&1 >/dev/null
        touch -t $(date -d $(jq .[0].dateString nightscout/glucose.json | tr -d '"') +%Y%m%d%H%M.%S) /tmp/mdt_cgm_uploaded
        echo "Uploaded $(jq '. | length' nightscout/uploaded-entries.json) missing entries"
        echo MDT CGM data uploaded
    else
        echo No missing entries found
    fi
}




die() {
    echo "$@"
    exit 1
}

main "$@"
