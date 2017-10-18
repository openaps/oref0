#!/bin/bash
#echo Starting ns-loop at $(date): && openaps get-ns-bg; sensors -u 2>/dev/null | awk '$NF > 85' | grep input || ( openaps ns-temptargets && echo -n Refreshed temptargets && openaps ns-meal-carbs && echo \\\" and meal-carbs\\\" && openaps upload )

# main ns-loop
main() {
    echo
    echo Starting oref0-ns-loop at $(date):
    get_ns_bg
    overtemp && exit 1
    ns_temptargets || die "ns_temptargets failed"
    ns_meal_carbs || die ", but ns_meal_carbs failed"
    upload
    echo Completed oref0-ns-loop at $(date)
}

function overtemp {
    # check for CPU temperature above 85°C
    sensors -u 2>/dev/null | awk '$NF > 85' | grep input \
    && echo Edison is too hot: waiting for it to cool down at $(date)\
    && echo Please ensure rig is properly ventilated
}

#openaps get-ns-glucose && cat cgm/ns-glucose.json | json -c \\\"minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38\\\" | grep -q glucose && cp -pu cgm/ns-glucose.json cgm/glucose.json; cp -pu cgm/glucose.json monitor/glucose.json
function get_ns_bg {
    openaps get-ns-glucose > /dev/null
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

function find_valid_ns_glucose {
    cat cgm/ns-glucose.json | json -c "minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38"
}

function ns_temptargets {
    #openaps report invoke settings/temptargets.json settings/profile.json >/dev/null
    nightscout ns $NIGHTSCOUT_HOST $API_SECRET temp_targets > settings/ns-temptargets.json
    # TODO: merge local-temptargets.json with ns-temptargets.json
    #openaps report invoke settings/ns-temptargets.json settings/profile.json
    echo -n "Refreshed NS temptargets: "
    cat settings/ns-temptargets.json | jq -c -C '.[0] | { target: .targetBottom, duration: .duration, start: .created_at }'
    echo -n "Merging local temptargets: "
    cat settings/local-temptargets.json | jq -c -C '.[0] | { target: .targetBottom, duration: .duration, start: .created_at }'
    jq -s '.[0] + .[1]|unique|sort_by(.created_at)|reverse' settings/ns-temptargets.json settings/local-temptargets.json > settings/temptargets.json
    echo -n "Temptargets merged: "
    cat settings/temptargets.json | jq -c -C '.[0] | { target: .targetBottom, duration: .duration, start: .created_at }'
    oref0-get-profile settings/settings.json settings/bg_targets.json settings/insulin_sensitivities.json settings/basal_profile.json preferences.json settings/carb_ratios.json settings/temptargets.json --model=settings/model.json --autotune settings/autotune.json | jq . > settings/profile.json || die "Couldn't refresh profile"
}

# openaps report invoke monitor/carbhistory.json; oref0-meal monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new; grep -q COB monitor/meal.json.new && mv monitor/meal.json.new monitor/meal.json; exit 0
function ns_meal_carbs {
    openaps report invoke monitor/carbhistory.json >/dev/null
    oref0-meal monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new
    grep -q COB monitor/meal.json.new && mv monitor/meal.json.new monitor/meal.json
    echo -n "Refreshed carbhistory; COB: "
    grep COB monitor/meal.json | jq .mealCOB
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
function format_ns_status {
    ns-status monitor/clock-zoned.json monitor/iob.json enact/suggested.json enact/enacted.json monitor/battery.json monitor/reservoir.json monitor/status.json > upload/ns-status.json
}

#openaps format-latest-nightscout-treatments && test $(json -f upload/latest-treatments.json -a created_at eventType | wc -l ) -gt 0 && (ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json upload/latest-treatments.json ) || echo \\\"No recent treatments to upload\\\"
function upload_recent_treatments {
    #echo Uploading treatments
    format_latest_nightscout_treatments || die "Couldn't format latest NS treatments"
    if test $(json -f upload/latest-treatments.json -a created_at eventType | wc -l ) -gt 0; then
        ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json upload/latest-treatments.json || die "Couldn't upload latest treatments to NS"
        echo ed successfully
    else
        echo "No recent treatments to upload"
    fi
}

#nightscout cull-latest-openaps-treatments monitor/pumphistory-zoned.json settings/model.json $(openaps latest-ns-treatment-time) > upload/latest-treatments.json
function format_latest_nightscout_treatments {
    nightscout cull-latest-openaps-treatments monitor/pumphistory-zoned.json settings/model.json $(openaps latest-ns-treatment-time) > upload/latest-treatments.json
}

die() {
    echo "$@"
    exit 1
}

main "$@"
