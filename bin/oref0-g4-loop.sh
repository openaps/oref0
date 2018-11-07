#!/usr/bin/env bash
# main g4-loop
main() {
    echo
    echo Starting oref0-g4-loop at $(date):
    prep
    show_last_record
    check_for_cgm
    if ! enough_data; then
        echo "cgm/g4-glucose.json has < 24h worth of data"
        full_refresh
    elif ! glucose_lt_1h_old ; then
        echo cgm/g4-glucose.json more than 1h old:
        ls -la cgm/g4-glucose.json
        full_refresh
    elif glucose_fresh; then
        echo "cgm/g4-glucose.json < 5m old"
    else
        wait_if_needed
        echo Updating data
        update_data
        g4update -u 2>&1
    fi

    show_last_record
    if clock_diff; then
        echo -n "Setting G4 clock to: "
        g4setclock now
    fi
    echo Completed oref0-g4-loop at $(date)
}

function clock_diff {
    tail -25 /var/log/openaps/cgm-loop.log | egrep -q "clock diff.*[1-9]m"
}

function show_last_record {
    cat cgm/cgm-glucose.json | jq -c -C '.[0] | { sgv: .sgv, dateString: .dateString }'
}

function enough_data {
    jq --exit-status '. | length > 288' cgm/g4-glucose.json > /dev/null
}

function touch_glucose {
    if jq .[0].date/1000 cgm/g4-glucose.json >/dev/null; then
        touch -d "$(date -R -d @$(jq .[0].date/1000 cgm/g4-glucose.json))" cgm/g4-glucose.json
    fi
    if jq .[0].date/1000 cgm/cgm-glucose.json >/dev/null; then
        touch -d "$(date -R -d @$(jq .[0].date/1000 cgm/cgm-glucose.json))" cgm/cgm-glucose.json
    fi
}

function glucose_lt_1h_old {
    # check whether g4-glucose.json is less than 60m old
    touch_glucose
    find cgm -mmin -60 | egrep -q "g4-glucose.json"
}

function wait_if_needed {
    touch_glucose
    # as long as CGM data is less than 6m old, sleep
    while find cgm -mmin -6 | egrep -q "g4-glucose.json"; do
        echo -n "."
        sleep 10
    done
}

function glucose_fresh {
    # check whether g4-glucose.json is less than 5m old
    touch_glucose
    find cgm -mmin -6 | egrep -q "g4-glucose.json"
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
    rm cgm/g4-glucose.json
    g4update -f cgm/g4-glucose.json -u -b 30h -k 48h 2>&1
    cal_raw
}
function update_data {
    g4update -f cgm/g4-glucose.json -u -b 1h -k 48h 2>&1
    cal_raw
}

function cal_raw {
    get_cal_records
    add_raw_sgvs
}

function get_cal_records {
    cat cgm/g4-glucose.json | jq 'map(select(.type | contains("cal")))' > cgm/cal.json
    echo -n "Found "
    cat cgm/cal.json | jq '. | length' | tr -d '\n'
    echo " calibration records."
}

function add_raw_sgvs {
    oref0 raw cgm/g4-glucose.json cgm/cal.json 160 | jq . > cgm/cgm-glucose.json
    touch_glucose
    ls -la cgm/cgm-glucose.json cgm/glucose.json
    cp -pu cgm/cgm-glucose.json cgm/glucose.json
}

function check_for_cgm {
    if ! usb_connected && ! ble_configured; then
        echo CGM not connected via USB OTG, and not configured for BLE
        echo Aborting oref0-g4-loop at $(date)
        exit 2
    fi
}

function usb_connected {
    lsusb | grep 22a3
}

function ble_configured {
    crontab -l | egrep "^DEXCOM_CGM_ID=SM"
}

die() {
    echo "$@"
    exit 1
}

main "$@"
