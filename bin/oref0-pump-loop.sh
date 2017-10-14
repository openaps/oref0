#!/bin/bash

# main pump-loop
main() {
    prep
    if ! overtemp; then
        until( \
            echo && echo Starting pump-loop at $(date): \
            && wait_for_bg \
            && wait_for_silence \
            && if_mdt_get_bg \
            && refresh_old_pumphistory_enact \
            && refresh_old_pumphistory_24h \
            && refresh_old_profile \
            && touch /tmp/pump_loop_enacted -r monitor/glucose.json \
            && ( refresh_temp_and_enact || ( smb_verify_status && refresh_temp_and_enact ) ) \
            && refresh_pumphistory_and_enact \
            && refresh_profile \
            && refresh_pumphistory_24h \
            && echo Completed pump-loop at $(date) \
            && touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted \
            && echo); do

                if grep -q "percent" monitor/temp_basal.json; then
                    echo "Pssst! Your pump is set to % basal type. The pump won’t accept temporary basal rates in this mode. Change it to absolute u/hr, and temporary basal rates will then be able to be set."
                fi
                # On a random subset of failures, mmtune
                echo Error, retrying \
                && maybe_mmtune
                sleep 5
        done
    fi
}

# main supermicrobolus loop
smb_main() {
    prep
    if ! overtemp; then
        if ! ( \
            prep
            # checking to see if the log reports out that it is on % basal type, which blocks remote temps being set
            echo && echo Starting supermicrobolus pump-loop at $(date) with $upto30s second wait_for_silence: \
            && wait_for_bg \
            && wait_for_silence $upto30s \
            && ( preflight || preflight ) \
            && if_mdt_get_bg \
            && refresh_old_pumphistory_24h \
            && refresh_old_profile \
            && touch /tmp/pump_loop_enacted -r monitor/glucose.json \
            && ( smb_check_everything \
                && if (grep -q '"units":' enact/smb-suggested.json); then
                    ( smb_bolus && \
                        touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted \
                    ) \
                    || ( smb_old_temp && ( \
                        echo "Falling back to normal pump-loop" \
                        && refresh_temp_and_enact \
                        && refresh_pumphistory_and_enact \
                        && refresh_profile \
                        && refresh_pumphistory_24h \
                        && echo Completed pump-loop at $(date) \
                        && echo \
                        ))
                fi
                ) \
                && ( refresh_profile 15; refresh_pumphistory_24h; true ) \
                && refresh_after_bolus_or_enact \
                && echo Completed supermicrobolus pump-loop at $(date): \
                && touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted \
                && echo \
        ); then
            echo -n "SMB pump-loop failed. "
            if grep -q "percent" monitor/temp_basal.json; then
                echo "Pssst! Your pump is set to % basal type. The pump won’t accept temporary basal rates in this mode. Change it to absolute u/hr, and temporary basal rates will then be able to be set."
            fi
            maybe_mmtune
            echo Unsuccessful supermicrobolus pump-loop at $(date)
        fi
    fi
}

function overtemp {
    # check for CPU temperature above 85°C
    sensors -u 2>/dev/null | awk '$NF > 85' | grep input \
    && echo Rig is too hot: not running pump-loop at $(date)\
    && echo Please ensure rig is properly ventilated
}
function smb_reservoir_before {
    # Refresh reservoir.json and pumphistory.json
    gather \
    && cp monitor/reservoir.json monitor/lastreservoir.json \
    && openaps report invoke monitor/clock.json monitor/clock-zoned.json 2>&1 >/dev/null | tail -1 \
    && echo -n "Checking pump clock: " && (cat monitor/clock-zoned.json; echo) | tr -d '\n' \
    && echo -n " is within 1m of current time: " && date \
    && if (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") < -60 )) || (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") > 60 )); then
        echo Pump clock is more than 1m off: attempting to reset it
        oref0-set-device-clocks
       fi \
    && (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") > -60 )) \
    && (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") < 60 )) \
    && echo -n "and that pumphistory is less than 1m old.  " \
    && (find monitor/ -mmin -1 -size +5c | grep -q pumphistory)

}

# check if the temp was read more than 5m ago, or has been running more than 10m
function smb_old_temp {
    (find monitor/ -mmin +5 -size +5c | grep -q temp_basal && echo temp_basal.json more than 5m old) \
    || ( jq --exit-status "(.duration-1) % 30 < 20" monitor/temp_basal.json > /dev/null \
        && echo -n "Temp basal set more than 10m ago: " && jq .duration monitor/temp_basal.json
        )
}

# make sure everything is in the right condition to SMB
function smb_check_everything {
    # wait_for_silence and retry if first attempt fails
    smb_reservoir_before \
    && smb_enact_temp \
    && if (grep -q '"units":' enact/smb-suggested.json); then
        ( smb_verify_suggested || smb_suggest ) \
        && echo -n "Listening for $upto10s s silence: " && wait_for_silence $upto10s \
        && smb_verify_reservoir \
        && smb_verify_status \
        || ( echo Retrying SMB checks
            wait_for_silence 10
            smb_verify_status \
            && smb_reservoir_before \
            && smb_enact_temp \
            && ( smb_verify_suggested || smb_suggest ) \
            && smb_verify_reservoir \
            && smb_verify_status
            )
    else
        echo -n "No bolus needed (yet). "
    fi
}

function smb_suggest {
    rm -rf enact/smb-suggested.json
    ls enact/smb-suggested.json 2>/dev/null >/dev/null && die "enact/suggested.json present"
    # Run determine-basal
    echo -n Temp refresh && openaps report invoke monitor/temp_basal.json monitor/clock.json monitor/clock-zoned.json monitor/iob.json 2>&1 >/dev/null | tail -1 && echo ed \
    && openaps report invoke enact/smb-suggested.json 2>&1 >/dev/null \
    && cp -up enact/smb-suggested.json enact/suggested.json \
    && smb_verify_suggested
}

# enact the appropriate temp before SMB'ing, (only if smb_verify_enacted fails)
function smb_enact_temp {
    smb_suggest \
    && if ( echo -n "enact/smb-suggested.json: " && cat enact/smb-suggested.json | jq -C -c . && grep -q duration enact/smb-suggested.json && ! smb_verify_enacted ); then (
        rm enact/smb-enacted.json
        openaps report invoke enact/smb-enacted.json 2>&1 >/dev/null | tail -1
        grep -q duration enact/smb-enacted.json || openaps invoke enact/smb-enacted.json 2>&1 >/dev/null | tail -1
        cp -up enact/smb-enacted.json enact/enacted.json
        echo -n "enact/smb-enacted.json: " && cat enact/smb-enacted.json | jq -C -c '. | "Rate: \(.rate) Duration: \(.duration)"'
        ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    else
        echo -n "No smb_enact needed. "
    fi \
    && ( smb_verify_enacted || ( smb_verify_status; smb_verify_enacted) )
}

function smb_verify_enacted {
    # Read the currently running temp and
    # verify rate matches (within 0.03U/hr) and duration is no shorter than 5m less than smb-suggested.json
    rm -rf monitor/temp_basal.json
    ( echo -n Temp refresh \
        && ( openaps report invoke monitor/temp_basal.json || openaps report invoke monitor/temp_basal.json ) \
        2>&1 >/dev/null | tail -1 && echo -n "ed: " \
    ) && echo -n "monitor/temp_basal.json: " && cat monitor/temp_basal.json | jq -C -c . \
    && jq --slurp --exit-status 'if .[1].rate then (.[0].rate > .[1].rate - 0.03 and .[0].rate < .[1].rate + 0.03 and .[0].duration > .[1].duration - 5) else true end' monitor/temp_basal.json enact/smb-suggested.json > /dev/null
}

function smb_verify_reservoir {
    # Read the pump reservoir volume and verify it is within 0.1U of the expected volume
    rm -rf monitor/reservoir.json
    echo -n "Checking reservoir: " \
    && (openaps invoke monitor/reservoir.json || openaps invoke monitor/reservoir.json) 2>&1 >/dev/null | tail -1 \
    && echo -n "reservoir level before: " \
    && cat monitor/lastreservoir.json \
    && echo -n ", suggested: " \
    && jq -r -C -c .reservoir enact/smb-suggested.json | tr -d '\n' \
    && echo -n " and after: " \
    && cat monitor/reservoir.json && echo \
    && (( $(bc <<< "$(< monitor/lastreservoir.json) - $(< monitor/reservoir.json) <= 0.1") )) \
    && (( $(bc <<< "$(< monitor/lastreservoir.json) - $(< monitor/reservoir.json) >= 0") )) \
    && (( $(bc <<< "$(jq -r .reservoir enact/smb-suggested.json | tr -d '\n') - $(< monitor/reservoir.json) <= 0.1") )) \
    && (( $(bc <<< "$(jq -r .reservoir enact/smb-suggested.json | tr -d '\n') - $(< monitor/reservoir.json) >= 0") ))
}

function smb_verify_suggested {
    if grep incorrectly enact/smb-suggested.json; then
        echo "Checking system clock against pump clock:"
        oref0-set-system-clock 2>&1 >/dev/null
    fi
    echo -n "Checking deliverAt: " && jq -r .deliverAt enact/smb-suggested.json | tr -d '\n' \
    && echo -n " is within 1m of current time: " && date \
    && (( $(bc <<< "$(date +%s -d $(jq -r .deliverAt enact/smb-suggested.json | tr -d '\n')) - $(date +%s)") > -60 )) \
    && (( $(bc <<< "$(date +%s -d $(jq -r .deliverAt enact/smb-suggested.json | tr -d '\n')) - $(date +%s)") < 60 )) \
    && echo "and that smb-suggested.json is less than 1m old" \
    && (find enact/ -mmin -1 -size +5c | grep -q smb-suggested.json)
}

function smb_verify_status {
    # Read the pump status and verify it is not bolusing
    rm -rf monitor/status.json
    echo -n "Checking pump status (suspended/bolusing): "
    ( openaps invoke monitor/status.json || openaps invoke monitor/status.json ) 2>&1 >/dev/null | tail -1 \
    && cat monitor/status.json | jq -C -c . \
    && grep -q '"status": "normal"' monitor/status.json \
    && grep -q '"bolusing": false' monitor/status.json \
    && if grep -q '"suspended": true' monitor/status.json; then
        echo -n "Pump suspended; "
        unsuspend_if_no_temp
        gather
        false
    fi
}

function smb_bolus {
    # Verify that the suggested.json is less than 5 minutes old
    # and administer the supermicrobolus
    find enact/ -mmin -5 | grep smb-suggested.json > /dev/null \
    && if (grep -q '"units":' enact/smb-suggested.json); then
        openaps report invoke enact/bolused.json 2>&1 >/dev/null | tail -1 \
        && echo -n "enact/bolused.json: " && cat enact/bolused.json | jq -C -c . \
        && rm -rf enact/smb-suggested.json
    else
        echo "No bolus needed (yet)"
    fi
}

function refresh_after_bolus_or_enact {
    if (find enact/ -mmin -2 -size +5c | grep -q bolused.json || (cat monitor/temp_basal.json | json -c "this.duration > 28" | grep -q duration)); then
        # refresh profile if >5m old to give SMB a chance to deliver
        refresh_profile 3
        gather || ( wait_for_silence 10 && gather ) || ( wait_for_silence 20 && gather )
        openaps report invoke monitor/iob.json enact/smb-suggested.json 2>/dev/null >/dev/null \
        && cp -up enact/smb-suggested.json enact/suggested.json \
        && echo -n "IOB: " && cat enact/smb-suggested.json | jq .IOB
        true
    fi

}

function unsuspend_if_no_temp {
    # If temp basal duration is zero, unsuspend pump
    if (cat monitor/temp_basal.json | json -c "this.duration == 0" | grep -q duration); then
        if (grep -iq '"unsuspend_if_no_temp": true' preferences.json); then
            echo Temp basal has ended: unsuspending pump
            openaps use pump resume_pump
        else
            echo unsuspend_if_no_temp not enabled in preferences.json: leaving pump suspended
        fi
    else
        # If temp basal duration is > zero, do nothing
        echo Temp basal still running: leaving pump suspended
    fi
}

# calculate random sleep intervals, and get TTY port
function prep {
    set -o pipefail

    upto10s=$[ ( $RANDOM / 3277 + 1) ]
    upto20s=$[ ( $RANDOM / 1638 + 1) ]
    upto30s=$[ ( $RANDOM / 1092 + 1) ]
    # read tty port from pump.ini
    eval $(grep port pump.ini | sed "s/ //g")
    # if that fails, try the Explorer board default port
    if [ -z $port ]; then
        port=/dev/spidev5.1
    fi
}

function if_mdt_get_bg {
    echo -n
    if grep "MDT cgm" openaps.ini 2>&1 >/dev/null; then
        echo \
        && echo Attempting to retrieve MDT CGM data from pump
        #due to sometimes the pump is not in a state to give this command repeat until it completes
        #"decocare.errors.DataTransferCorruptionError: Page size too short"
        n=0
        until [ $n -ge 3 ]; do
            openaps report invoke monitor/cgm-mm-glucosedirty.json 2>&1 >/dev/null && break
            echo
            echo CGM data retrieval from pump disrupted, retrying in 5 seconds...
            n=$[$n+1]
            sleep 5;
            echo Reattempting to retrieve MDT CGM data
        done
        if [ -f "monitor/cgm-mm-glucosedirty.json" ]; then
            if [ -f "cgm/glucose.json" ]; then
                if [ $(date -d $(jq .[1].date monitor/cgm-mm-glucosedirty.json | tr -d '"') +%s) == $(date -d $(jq .[0].display_time monitor/glucose.json | tr -d '"') +%s) ]; then
                    echo MDT CGM data retrieved \
                    && echo No new MDT CGM data to reformat \
                    && echo
                    # TODO: remove if still unused at next oref0 release
                    # if you want to wait for new bg uncomment next lines and add a backslash after echo above
                    #&& wait_for_mdt_get_bg \
                    #&& mdt_get_bg
                else
                    mdt_get_bg
                fi
            else
                mdt_get_bg
            fi
        else
            echo "Unable to get cgm data from pump"
        fi
    fi
}
# TODO: remove if still unused at next oref0 release
function wait_for_mdt_get_bg {
    # This might not really be needed since very seldom does a loop take less time to run than CGM Data takes to refresh.
    until [ $(date --date="@$(($(date -d $(jq .[1].date monitor/cgm-mm-glucosedirty.json| tr -d '"') +%s) + 300))" +%s) -lt $(date +%s) ]; do
        CGMDIFFTIME=$(( $(date --date="@$(($(date -d $(jq .[1].date monitor/cgm-mm-glucosedirty.json| tr -d '"') +%s) + 300))" +%s) - $(date +%s) ))
        echo "Last CGM Time was $(date -d $(jq .[1].date monitor/cgm-mm-glucosedirty.json| tr -d '"') +"%r") wait untill $(date --date="@$(($(date #-d $(jq .[1].date monitor/cgm-mm-glucosedirty.json| tr -d '"') +%s) + 300))" +"%r")to continue"
        echo "waiting for $CGMDIFFTIME seconds before continuing"
        sleep $CGMDIFFTIME
        until openaps report invoke monitor/cgm-mm-glucosedirty.json 2>&1 >/dev/null; do
            echo cgm data from pump disrupted, retrying in 5 seconds...
            sleep 5;
            echo -n MDT cgm data retrieve
        done
    done
}
function mdt_get_bg {
    openaps report invoke monitor/cgm-mm-glucosetrend.json 2>&1 >/dev/null \
    && openaps report invoke cgm/cgm-glucose.json 2>&1 >/dev/null \
    && grep -q glucose cgm/cgm-glucose.json \
    && echo MDT CGM data retrieved \
    && cp -pu cgm/cgm-glucose.json cgm/glucose.json \
    && cp -pu cgm/glucose.json monitor/glucose-unzoned.json \
    && echo -n MDT New cgm data reformat \
    && openaps report invoke monitor/glucose.json 2>&1 >/dev/null \
    && openaps report invoke nightscout/glucose.json 2>&1 >/dev/null \
    && echo ted
}
# make sure we can talk to the pump and get a valid model number
function preflight {
    echo -n "Preflight "
    # only 515, 522, 523, 715, 722, 723, 554, and 754 pump models have been tested with SMB
    ( openaps report invoke settings/model.json || openaps report invoke settings/model.json ) 2>&1 >/dev/null | tail -1 \
    && ( egrep -q "[57](15|22|23|54)" settings/model.json || (grep 12 settings/model.json && echo -n "error: pump model untested with SMB: "; false) ) \
    && echo -n "OK. " \
    || ( echo -n "fail. "; false )
}

# reset radio, init world wide pump (if applicable), mmtune, and wait_for_silence 60 if no signal
function mmtune {
    # TODO: remove reset_spi_serial.py once oref0_init_pump_comms.py is fixed to do it correctly
    if [[ $port == "/dev/spidev5.1" ]]; then
        reset_spi_serial.py 2>/dev/null
    fi
    oref0_init_pump_comms.py
    echo -n "Listening for 40s silence before mmtuning: "
    for i in $(seq 1 800); do
        echo -n .
        any_pump_comms 40 2>/dev/null | egrep -v subg | egrep No \
        && break
    done
    echo {} > monitor/mmtune.json
    echo -n "mmtune: " && openaps report invoke monitor/mmtune.json 2>&1 >/dev/null | tail -1
    grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | while read line
        do echo -n "$line "
    done
    rssi_wait=$(grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | tail -1 | awk '($1 < -60) {print -($1+60)*2}')
    if [[ $rssi_wait > 1 ]]; then
        echo "waiting for $rssi_wait second silence before continuing"
        wait_for_silence $rssi_wait
        echo "Done waiting for rigs with better signal."
    fi
}

function maybe_mmtune {
    if ( find /tmp/ -mmin -15 | egrep -q "pump_loop_completed" ); then
        # mmtune ~ 25% of the time
        [[ $(( ( RANDOM % 100 ) )) > 75 ]] \
        && echo "Waiting for 40s silence before mmtuning" \
        && wait_for_silence 40 \
        && mmtune
    else
        echo "pump_loop_completed more than 15m old; waiting for 40s silence before mmtuning"
        wait_for_silence 40
        mmtune
    fi
}

function any_pump_comms {
    mmeowlink-any-pump-comms.py --port $port --wait-for $1
}

# listen for $1 seconds of silence (no other rigs talking to pump) before continuing
function wait_for_silence {
    if [ -z $1 ]; then
        waitfor=40
    else
        waitfor=$1
    fi
    # check radio multiple times, and mmtune if all checks fail
    ( ( out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
      ( echo -n .; sleep 1; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
      ( echo -n .; sleep 2; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
      ( echo -n .; sleep 4; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
      ( echo -n .; sleep 8; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) )
    ) 2>&1 | tail -2 \
        && echo -n "Radio ok. " || (echo -n "Radio check failed. "; any_pump_comms 1 2>&1 | tail -1; mmtune)
    echo -n "Listening: "
    for i in $(seq 1 800); do
        echo -n .
        any_pump_comms $waitfor 2>/dev/null | egrep -v subg | egrep No \
        && break
    done
}

# Refresh pumphistory etc.
function gather {
    openaps report invoke monitor/status.json 2>&1 >/dev/null | tail -1 \
    && echo -n Ref \
    && ( grep -q "model.*12" monitor/status.json || \
         test $(cat monitor/status.json | json suspended) == true || \
         test $(cat monitor/status.json | json bolusing) == false ) \
    && echo -n resh \
    && ( openaps monitor-pump || openaps monitor-pump ) 2>&1 >/dev/null | tail -1 \
    && echo -n ed \
    && merge_pumphistory \
    && echo -n " pumphistory" \
    && openaps report invoke monitor/meal.json 2>&1 >/dev/null | tail -1 \
    && echo " and meal.json" \
    || (echo; exit 1) 2>/dev/null
}

function merge_pumphistory {
    jq -s '.[0] + .[1]|unique|sort_by(.timestamp)|reverse' monitor/pumphistory-zoned.json settings/pumphistory-24h-zoned.json > monitor/pumphistory-merged.json
}

# Calculate new suggested temp basal and enact it
function enact {
    rm enact/suggested.json
    openaps report invoke enact/suggested.json \
    && if (cat enact/suggested.json && grep -q duration enact/suggested.json); then (
        rm enact/enacted.json
        openaps report invoke enact/enacted.json 2>&1 >/dev/null | tail -1
        grep -q duration enact/enacted.json || openaps invoke enact/enacted.json ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    fi
    grep incorrectly enact/suggested.json && oref0-set-system-clock 2>/dev/null
    echo -n "enact/enacted.json: " && cat enact/enacted.json | jq -C -c .
}

# refresh pumphistory if it's more than 15m old and enact
function refresh_old_pumphistory_enact {
    find monitor/ -mmin -15 -size +100c | grep -q pumphistory-zoned \
    || ( echo -n "Old pumphistory: " && gather && enact )
}

# refresh pumphistory if it's more than 30m old, but don't enact
function refresh_old_pumphistory {
    find monitor/ -mmin -30 -size +100c | grep -q pumphistory-zoned \
    || ( echo -n "Old pumphistory, waiting for $upto30s seconds of silence: " && wait_for_silence $upto30s && gather )
}

# refresh pumphistory_24h if it's more than 2h old
function refresh_old_pumphistory_24h {
    find settings/ -mmin -120 -size +100c | grep -q pumphistory-24h-zoned \
    || ( echo -n "Old pumphistory-24h, waiting for $upto30s seconds of silence: " && wait_for_silence $upto30s \
        && echo -n Old pumphistory-24h refresh \
        && openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>&1 >/dev/null | tail -1 && echo ed )
}

# refresh settings/profile if it's more than 1h old
function refresh_old_profile {
    find settings/ -mmin -60 -size +5c | grep -q settings/profile.json && echo -n "Profile less than 60m old. " \
    || (echo -n Old settings refresh && openaps get-settings 2>&1 >/dev/null | tail -1 && echo -n "ed. " )
}

function refresh_smb_temp_and_enact {
    # set mtime of monitor/glucose.json to the time of its most recent glucose value
    setglucosetimestamp
    # only smb_enact_temp if we haven't successfully completed a pump_loop recently
    # (no point in enacting a temp that's going to get changed after we see our last SMB)
    if (cat monitor/temp_basal.json | json -c "this.duration > 20" | grep -q duration); then
        echo -n "Temp duration >20m. "
    elif ( find /tmp/ -mmin +10 | grep -q /tmp/pump_loop_completed ); then
        echo "pump_loop_completed more than 10m ago: setting temp before refreshing pumphistory. "
        smb_enact_temp
    else
        echo -n "pump_loop_completed less than 10m ago. "
    fi
}

function refresh_temp_and_enact {
    # set mtime of monitor/glucose.json to the time of its most recent glucose value
    setglucosetimestamp
    # TODO: use pump_loop_completed logic as in refresh_smb_temp_and_enact
    if( (find monitor/ -newer monitor/temp_basal.json | grep -q glucose.json && echo -n "glucose.json newer than temp_basal.json. " ) \
        || (! find monitor/ -mmin -5 -size +5c | grep -q temp_basal && echo "temp_basal.json more than 5m old. ")); then
            (echo -n Temp refresh && openaps report invoke monitor/temp_basal.json monitor/clock.json monitor/clock-zoned.json monitor/iob.json 2>&1 >/dev/null | tail -1 && echo ed \
            && if (cat monitor/temp_basal.json | json -c "this.duration < 27" | grep -q duration); then
                enact; else echo Temp duration 27m or more
            fi)
    else
        echo -n "temp_basal.json less than 5m old. "
    fi
}

function refresh_pumphistory_and_enact {
    # set mtime of monitor/glucose.json to the time of its most recent glucose value
    setglucosetimestamp
    if ((find monitor/ -newer monitor/pumphistory-zoned.json | grep -q glucose.json && echo -n "glucose.json newer than pumphistory. ") \
        || (find enact/ -newer monitor/pumphistory-zoned.json | grep -q enacted.json && echo -n "enacted.json newer than pumphistory. ") \
        || ((! find monitor/ -mmin -5 | grep -q pumphistory-zoned || ! find monitor/ -mmin +0 | grep -q pumphistory-zoned) && echo -n "pumphistory more than 5m old. ") ); then
            (echo -n ": " && gather && enact )
    else
        echo Pumphistory less than 5m old
    fi
}

function refresh_profile {
    if [ -z $1 ]; then
        profileage=10
    else
        profileage=$1
    fi
    find settings/ -mmin -$profileage -size +5c | grep -q settings.json && echo -n "Settings less than $profileage minutes old. " \
    || (echo -n Settings refresh && openaps get-settings 2>/dev/null >/dev/null && echo -n "ed. ")
}

function wait_for_bg {
    if grep "MDT cgm" openaps.ini 2>&1 >/dev/null; then
        echo "MDT CGM configured; not waiting"
    elif egrep -q "Waiting 0.[0-9]m to microbolus again." enact/smb-suggested.json; then
        echo "Retrying microbolus without waiting for new BG"
    else
        echo -n "Waiting up to 4 minutes for new BG: "
        for i in `seq 1 24`; do
            # set mtime of monitor/glucose.json to the time of its most recent glucose value
            touch -d "$(date -R -d @$(jq .[0].date/1000 monitor/glucose.json))" monitor/glucose.json
            if (! ls /tmp/pump_loop_completed >/dev/null ); then
                break
            elif (find monitor/ -newer /tmp/pump_loop_completed | grep -q glucose.json); then
                echo glucose.json newer than pump_loop_completed
                break
            else
                echo -n .; sleep 10
            fi
        done
    fi
}

function refresh_pumphistory_24h {
    if (! ls monitor/edison-battery.json 2>/dev/null >/dev/null); then
        echo -n "Edison battery level not found. "
        autosens_freq=15
    elif (jq --exit-status ".battery >= 98 or (.battery <= 70 and .battery >= 60)" monitor/edison-battery.json > /dev/null); then
        echo -n "Edison battery at $(jq .battery monitor/edison-battery.json)% is charged (>= 98%) or likely charging (60-70%). "
        autosens_freq=15
    elif (jq --exit-status ".battery < 98" monitor/edison-battery.json > /dev/null); then
        echo -n "Edison on battery: $(jq .battery monitor/edison-battery.json)%. "
        autosens_freq=30
    else
        echo -n "Edison battery level unknown. "
        autosens_freq=15
    fi
    find settings/ -mmin -$autosens_freq -size +100c | grep -q pumphistory-24h-zoned && echo "Pumphistory-24 < ${autosens_freq}m old" \
    || (echo -n pumphistory-24h refresh \
        && openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>&1 >/dev/null | tail -1 && echo ed)
}

function setglucosetimestamp {
    if grep "MDT cgm" openaps.ini 2>&1 >/dev/null; then
      touch -d "$(date -R -d @$(jq .[0].date/1000 nightscout/glucose.json))" monitor/glucose.json
    else
      touch -d "$(date -R -d @$(jq .[0].date/1000 monitor/glucose.json))" monitor/glucose.json
    fi
}

die() {
    echo "$@"
    exit 1
}

if [[ $1 == *"microbolus"* ]]; then
    smb_main "$@"
else
    main "$@"
fi
