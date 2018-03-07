#!/bin/bash
# main g4-loop
main() {
    echo
    echo Starting oref0-g4-loop at $(date):
    prep
    show_last_record
    if ! enough_data; then
        echo "cgm/g4-glucose.json has < 24h worth of data"
        full_refresh
    elif ! glucose_lt_1h_old ; then
        echo cgm/g4-glucose.json more than 1h old:
        ls -la cgm/g4-glucose.json
        full_refresh
    elif glucose_fresh; then
        echo "cgm/g4-glucose.json < 4m old"
    else
        wait_if_needed
        echo Updating data
        update_data
    fi

    show_last_record
    if clock_diff; then
        g4setclock now
    fi
    echo Completed oref0-g4-loop at $(date)
}

function clock_diff {
    tail -40 /var/log/openaps/cgm-loop.log | egrep "clock diff.*[1-9]m"
}

function show_last_record {
    cat cgm/g4-glucose.json | jq -c -C '.[0] | { sgv: .sgv, dateString: .dateString }'
}

function enough_data {
    jq --exit-status '. | length > 288' cgm/g4-glucose.json > /dev/null
}

function touch_glucose {
    if jq .[0].date/1000 cgm/g4-glucose.json >/dev/null; then
        touch -d "$(date -R -d @$(jq .[0].date/1000 cgm/g4-glucose.json))" cgm/g4-glucose.json
    fi
}

function glucose_lt_1h_old {
    # check whether g4-glucose.json is less than 60m old
    touch_glucose
    find cgm -mmin -60 | egrep -q "g4-glucose.json"
}

function wait_if_needed {
    touch_glucose
    # as long as CGM data is less than 5m old, sleep
    while find cgm -mmin -5 | egrep -q "g4-glucose.json"; do
        echo -n "."
        sleep 10
    done
}

function glucose_fresh {
    # check whether g4-glucose.json is less than 5m old
    touch_glucose
    find cgm -mmin -4 | egrep -q "g4-glucose.json"
}

function prep {
    if [[ -z $NIGHTSCOUT_SITE ]]; then
        if [[ -z $NIGHTSCOUT_HOST ]]; then
            echo Warning: NIGHTSCOUT_SITE / NIGHTSCOUT_HOST not set
        else
            export NIGHTSCOUT_SITE=$NIGHTSCOUT_HOST
        fi
    fi
    if [[ -z $NIGHTSCOUT_API_SECRET ]]; then
        if [[ -z $API_SECRET ]]; then
            echo Warning: NIGHTSCOUT_API_SECRET / API_SECRET not set
        else
            export NIGHTSCOUT_API_SECRET=$API_SECRET
        fi
    fi
}

function full_refresh {
    g4update -f cgm/g4-glucose.json -u -b 30h -k 48h 2>&1
}
function update_data {
    g4update -f cgm/g4-glucose.json -u -b 1h -k 48h 2>&1
}





die() {
    echo "$@"
    exit 1
}

main "$@"
