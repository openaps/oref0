#!/usr/bin/env bash
# updated cgm values from enlite sensors
# sould be called within pump-loop (and not in a separate loop) to avoid radio blocking issues.

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

FILE_MDT='monitor/cgm-mm-glucosedirty.json'
FILE_POST_TREND='cgm/cgm-glucose.json'
FILE_FINAL='cgm/glucose.json'

CS_TIME_SENSE=1

usage "$@" <<EOT
Usage: $self
Updates cgm histroy from enlite sensors and uploads to nightscout. Has to be started within pump-loop.
EOT

main() {
    echo
    echo Starting oref0-mdt-update at $(date):
    prep
    show_last_record
    if glucose_fresh; then
        echo "cgm data < 2.5m old"
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
    
    # delete empty source file
    if [ ! -s $FILE_MDT ]; then rm -f $FILE_MDT; fi
}

# Shows minimal version of first record in file.
function show_last_record {
    if [ ! -f $FILE_MDT ]; then echo "$FILE_MDT not found."; fi
    echo -n "Most recent cgm record: "
    jq -c -C 'sort_by(.date) | reverse | .[0] | { sgv: .sgv, dateString: .dateString }' $FILE_MDT
}

# Checks whether 2.5m has passed since newst cgm value
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
    if ! wait_for_silence $CS_TIME_SENSE ; then echo "Radio jammed"; exit 1; fi
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
    if ! wait_for_silence $CS_TIME_SENSE ; then echo "Radio jammed"; exit 1; fi
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
    jq -c 'del(.sgv) | del(.dateString) | del(.type)' | \
    jq -s '.' > $FILE_POST_TREND

    # wild copy party
    grep -q glucose $FILE_POST_TREND \
    && echo MDT CGM data retrieved \
    && cp -pu $FILE_POST_TREND $FILE_FINAL \
    && cp -pu $FILE_FINAL monitor/glucose.json \
    && echo -n MDT New cgm data reformat \
    && echo ted
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
