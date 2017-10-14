#!/bin/bash
#echo Starting ns-loop at $(date): && openaps get-ns-bg; sensors -u 2>/dev/null | awk '$NF > 85' | grep input || ( openaps ns-temptargets && echo -n Refreshed temptargets && openaps ns-meal-carbs && echo \\\" and meal-carbs\\\" && openaps upload )

# main pump-loop
main() {
    echo Starting ns-loop at $(date):
    get_ns_bg
    overtemp && exit 1
    ns_temptargets || die "ns_temptargets failed"
    echo -n Refreshed temptargets
    ns_meal_carbs || die "ns_meal_carbs failed"
    echo " and meal carbs"
    upload
    fi
}

function overtemp {
    # check for CPU temperature above 85°C
    sensors -u 2>/dev/null | awk '$NF > 85' | grep input \
    && echo Rig is too hot: waiting for it to cool down at $(date)\
    && echo Please ensure rig is properly ventilated
}

#openaps get-ns-glucose && cat cgm/ns-glucose.json | json -c \\\"minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38\\\" | grep -q glucose && cp -pu cgm/ns-glucose.json cgm/glucose.json; cp -pu cgm/glucose.json monitor/glucose.json
function get_ns_glucose {
    # if ns-glucose.json data is <10m old, no more than 5m in the future, and valid (>38),
    # copy cgm/ns-glucose.json over to cgm/glucose.json if it's newer
    cat cgm/ns-glucose.json | json -c "minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38" | grep -q glucose && cp -pu cgm/ns-glucose.json cgm/glucose.json
    # copy cgm/glucose.json over to monitor/glucose.json if it's newer
    cp -pu cgm/glucose.json monitor/glucose.json
}

function ns_temptargets {
    openaps report invoke settings/ns-temptargets.json settings/profile.json
    # TODO: merge local-temptargets.json with ns-temptargets.json
}

# openaps report invoke monitor/carbhistory.json; oref0-meal monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new; grep -q COB monitor/meal.json.new && mv monitor/meal.json.new monitor/meal.json; exit 0
function ns_meal_carbs {
    openaps report invoke monitor/carbhistory.json
    oref0-meal monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new
    grep -q COB monitor/meal.json.new && mv monitor/meal.json.new monitor/meal.json
    exit 0
}

# echo -n Upload && ( openaps upload-ns-status; openaps upload-pumphistory-entries; openaps upload-recent-treatments ) 2>/dev/null >/dev/null && echo ed
function upload {
    echo -n Upload 
    ( upload_ns_status; upload_recent_treatments ) 2>/dev/null >/dev/null || die " failed"
    echo ed
}

# grep -q iob monitor/iob.json && find enact/ -mmin -5 -size +5c | grep -q suggested.json && openaps format-ns-status && grep -q iob upload/ns-status.json && ns-upload $NIGHTSCOUT_HOST $API_SECRET devicestatus.json upload/ns-status.json
function upload_ns_status {
    grep -q iob monitor/iob.json \
    && find enact/ -mmin -5 -size +5c | grep -q suggested.json \
    && format_ns_status \
    && grep -q iob upload/ns-status.json \
    && ns-upload $NIGHTSCOUT_HOST $API_SECRET devicestatus.json upload/ns-status.json
}

#ns-status monitor/clock-zoned.json monitor/iob.json enact/suggested.json enact/enacted.json monitor/battery.json monitor/reservoir.json monitor/status.json > upload/ns-status.json
function format_ns_status {
    ns-status monitor/clock-zoned.json monitor/iob.json enact/suggested.json enact/enacted.json monitor/battery.json monitor/reservoir.json monitor/status.json > upload/ns-status.json
}

#openaps format-latest-nightscout-treatments && test $(json -f upload/latest-treatments.json -a created_at eventType | wc -l ) -gt 0 && (ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json upload/latest-treatments.json ) || echo \\\"No recent treatments to upload\\\"
function upload_recent_treatments {
    format_latest_nightscout_treatments \
    && test $(json -f upload/latest-treatments.json -a created_at eventType | wc -l ) -gt 0 \
    && (ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json upload/latest-treatments.json ) || echo \\\"No recent treatments to upload\\\"
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
