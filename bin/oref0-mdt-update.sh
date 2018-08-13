#!/bin/bash
# updates cgm values from enlite sensors
# sould be called within pump-loop (and not in a separate loop) to avoid radio blocking issues.

FILE_MDT='monitor/cgm-mm-glucosedirty.json'
FILE_POST_TREND='cgm/cgm-glucose.json'
FILE_FINAL='cgm/glucose.json'

CS_TIME_SENSE=1s
CS_TIME_WAIT=5s

usage "$@" <<EOT
Usage: $self
Updates cgm history from enlite sensors and uploads to Nightscout. Has to be started within pump-loop to avoid pump radio contention.
EOT

main() {
    echo
    echo Starting oref0-mdt-update at $(date):
    prep
    show_last_record
    if glucose_fresh; then
        echo "cgm data < 5m old"
    elif glucose_lt_1h_old; then
        echo "updating cgm data"
        update_data
        show_last_record
    else
        echo "full refresh of cgm data"
        full_refresh
        show_last_record
    fi

    echo Completed oref0-mdt-update at $(date)
}

# checks environment variables
function prep {
    # required
    if [[ -z $MEDTRONIC_PUMP_ID ]]; then
            echo "ERROR: MEDTRONIC_PUMP_ID not set! exit 1"
            exit 1
    fi
    if [[ -z $MEDTRONIC_FREQUENCY ]]; then
            echo "ERROR: MEDTRONIC_FREQUENCY not set! exit 1"
            exit 1
    fi
    
    # optional
    if [[ -z $NIGHTSCOUT_SITE ]]; then
        if [[ -z $NIGHTSCOUT_HOST ]]; then
            echo "Warning: NIGHTSCOUT_SITE / NIGHTSCOUT_HOST not set"
        else
            export NIGHTSCOUT_SITE=$NIGHTSCOUT_HOST
        fi
    fi
    if [[ -z $NIGHTSCOUT_API_SECRET ]]; then
        if [[ -z $API_SECRET ]]; then
            echo "Warning: NIGHTSCOUT_API_SECRET / API_SECRET not set"
        else
            export NIGHTSCOUT_API_SECRET=$API_SECRET
        fi
    fi
}

# Shows minimal version of first record in file.
function show_last_record {
    if [ ! -f $FILE_MDT ]; then echo "$FILE_MDT not found."; fi
    echo -n "Most recent cgm record: "
    jq -c -C 'sort_by(.date) | reverse | .[0] | { sgv: .sgv, dateString: .dateString }' $FILE_MDT
}

# Checks whether 5m has passed since newst cgm value
# returns 0 if ture, 1 if false
function glucose_fresh {
    if [ ! -f $FILE_MDT ]; then return 1; fi
    jq --exit-status "sort_by(.date) | reverse | .[0] | ($(date +%s) - .date / 1000) < 300" $FILE_MDT > /dev/null 
}

# Checks whether 60m has passed since newst cgm value
# returns 0 if ture, 1 if false
function glucose_lt_1h_old {
    if [ ! -f $FILE_MDT ]; then return 1; fi
    jq --exit-status "sort_by(.date) | reverse | .[0] | ($(date +%s) - .date / 1000) < 3600" $FILE_MDT > /dev/null 
}

# Removes old cgm data file and requests cgm history from pump
function full_refresh {
    clean_files
    listen_before_talk
    cgmupdate -f $FILE_MDT -u -b 30h -k 48h 2>&1
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq "0" ]; then
        trend_and_copy
    elif [ "$EXIT_CODE" -eq "2" ]; then
        echo "failed to upload cgm to nightscout"
        trend_and_copy
    else 
        echo "cgm full refresh failed."
        exit 1
    fi
}

# Updates local cgm data with just the last hour of pump request
function update_data {
    listen_before_talk
    cgmupdate -f $FILE_MDT -u -b 1h -k 48h 2>&1
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq "0" ]; then
        trend_and_copy
    elif [ "$EXIT_CODE" -eq "2" ]; then
        echo "failed to upload cgm to nightscout"
        trend_and_copy
    else 
        echo "cgm data update failed."
        exit 1
    fi
}

# Converts cgmupdate output to a format OpenAPS understands
function trend_and_copy {
    cat $FILE_MDT | \
    jq -c 'sort_by(.date) | reverse | .[] ' | \
    jq -c 'select(.type | contains ("sgv"))' | \
    jq -c '. + {"name": "GlucoseSensorData"} | . + {"date_type": "prevTimestamp"}' | \
    jq -c '. + {"glucose": .sgv}' | \
    jq -c '. + {"display_time": .dateString}' | \
    jq -c 'del(.sgv) | del(.date) | del(.dateString) | del(.type)' | \
    jq -s '.' > $FILE_POST_TREND

    # wild copy party
    grep -q glucose $FILE_POST_TREND \
    && echo MDT CGM data retrieved \
    && cp -pu $FILE_POST_TREND $FILE_FINAL \
    && cp -pu $FILE_FINAL monitor/glucose.json \
    && echo MDT New cgm data reformatted
}

# Listens for a free channel.
# Poor man's CSMA/CA 
#
# exits with code 1 if channel is jammed for more than 1000 rounds or waiting.
function listen_before_talk {
    # fast sense
    if listen -t $CS_TIME_SENSE 2>&1 ; then
        # wait for a free channel
        echo -n "Wait for radio silence:"
        for i in $(seq 1 1000); do
            echo -n .
            #there should pass some time until listen fails again:
            sleep $CS_TIME_WAIT 
            if ! listen -t $CS_TIME_WAIT 2>&1 ; then
                echo "radio channel is free!"
                return 0
            fi
        done
    else
        return 0
    fi
    echo "radio channel is jammed! exit 1"
    exit 1
}

# removes temporary and result files
function clean_files {
    rm $FILE_MDT
    rm $FILE_POST_TREND
    rm $FILE_FINAL
    rm monitor/glucose.json
}


die() {
    echo "$@"
    exit 1
}

main "$@"
