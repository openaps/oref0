#!/bin/bash

# OREF0_DEBUG makes this script much more verbose
# and allows it to print additional debug information.
# OREF0_DEBUG=1 generally means to print everything that usually
# goes to stderr. (It will will include stack traces in case
# of errors or exceptions in sub commands)
# OREF0_DEBUG=2 is for debugging only. It will print all commands
# being executed as well as all their output, (use with care as it
# might overflow your log files)
# The default value is 0. A silent mode could also be implemented, but
# it hasn't been done at this point.
# Note: for future changes:
# -  when subcommand outputs are not needed in the main log file:
#    - redirect the output to either fd >&3 or fd >&4 based on
#    - when you want the output visible.
OREF0_DEBUG=${OREF0_DEBUG:-0}
if [[ "$OREF0_DEBUG" -ge 1 ]] ; then
  exec 3>&1
else
  exec 3>/dev/null
fi
if [[ "$OREF0_DEBUG" -ge 2 ]] ; then
  exec 4>&1
  set -x
else
  exec 4>/dev/null
fi

# old pump-loop
old_main() {
    prep
    if ! overtemp; then
        until( \
            echo && echo Starting basal-only pump-loop at $(date): \
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
            && echo Completed basal-only pump-loop at $(date) \
            && touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted \
            && echo); do
                # checking to see if the log reports out that it is on % basal type, which blocks remote temps being set
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

# main pump-loop
main() {
    prep
    if ! overtemp; then
        echo && echo "Starting oref0-pump-loop at $(date) with $upto30s second wait_for_silence:"
        try_fail wait_for_bg
        try_fail wait_for_silence $upto30s
        retry_fail preflight
        try_fail if_mdt_get_bg
        try_fail refresh_old_pumphistory_24h
        try_fail refresh_old_profile
        try_fail touch /tmp/pump_loop_enacted -r monitor/glucose.json
        if smb_check_everything; then
            if ( grep -q '"units":' enact/smb-suggested.json 2>&3); then
                if try_return smb_bolus; then
                    touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted
                else
                    smb_old_temp && ( \
                    echo "Falling back to basal-only pump-loop" \
                    && refresh_temp_and_enact \
                    && refresh_pumphistory_and_enact \
                    && refresh_profile \
                    && refresh_pumphistory_24h \
                    && echo Completed pump-loop at $(date) \
                    && echo \
                    )
                fi
            fi
            touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted
            if ! glucose-fresh; then
                refresh_profile 15
                if ! glucose-fresh; then
                    refresh_pumphistory_24h
                    if ! glucose-fresh; then
                        refresh_after_bolus_or_enact
                    fi
                fi
            fi
            cat /tmp/oref0-updates.txt 2>&3
            echo Completed oref0-pump-loop at $(date)
            echo
        else
            # pump-loop errored out for some reason
            fail "$@"
        fi
    fi
}

function timerun {
    echo "$(date): running $@" >> /tmp/timefile.txt
    { time $@ 2> /tmp/stderr ; } 2>> /tmp/timefile.txt
    echo "$(date): completed $@" >> /tmp/timefile.txt
    cat /tmp/stderr 1>&2
}

function fail {
    echo -n "oref0-pump-loop failed. "
    if find enact/ -mmin -5 | grep smb-suggested.json >&4 && grep "too old" enact/smb-suggested.json >&4; then
        touch /tmp/pump_loop_completed
        wait_for_bg
        echo "Unsuccessful oref0-pump-loop (BG too old) at $(date)"
    # don't treat suspended pump as a complete failure
    elif find monitor/ -mmin -5 | grep status.json >&4 && grep -q '"suspended": true' monitor/status.json; then
        refresh_profile 15; refresh_pumphistory_24h
        refresh_after_bolus_or_enact
        echo "Incomplete oref0-pump-loop (pump suspended) at $(date)"
    else
        maybe_mmtune
        echo "If pump and rig are close enough, this error usually self-resolves. Stand by for the next loop."
        echo Unsuccessful oref0-pump-loop at $(date)
    fi
    if grep -q "percent" monitor/temp_basal.json; then
        echo "Error: pump is set to % basal type. The pump won’t accept temporary basal rates in this mode. Please change the pump to absolute u/hr so temporary basal rates will then be able to be set."
    fi
    if ! cat preferences.json | jq . >&4; then
        echo Error: syntax error in preferences.json: please go correct your typo.
    fi
    echo
    exit 1
}


function overtemp {
    # check for CPU temperature above 85°C
    sensors -u 2>&3 | awk '$NF > 85' | grep input \
    && echo Rig is too hot: not running pump-loop at $(date)\
    && echo Please ensure rig is properly ventilated
}

function smb_reservoir_before {
    # Refresh reservoir.json and pumphistory.json
    try_fail refresh_pumphistory_and_meal
    try_fail cp monitor/reservoir.json monitor/lastreservoir.json
    try_fail timerun openaps report invoke monitor/clock.json monitor/clock-zoned.json 2>&3 >&4 | tail -1
    echo -n "Checking pump clock: "
    (cat monitor/clock-zoned.json; echo) | tr -d '\n'
    echo -n " is within 90s of current time: " && date
    if (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") < -55 )) || (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") > 55 )); then
        echo Pump clock is more than 55s off: attempting to reset it
        timerun oref0-set-device-clocks
       fi
    (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") > -90 )) \
    && (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") < 90 )) || { echo "Error: pump clock refresh error / mismatch"; fail "$@"; }
    find monitor/ -mmin -1 -size +5c | grep -q pumphistory || { echo "Error: pumphistory too old"; fail "$@"; }
}

# check if the temp was read more than 5m ago, or has been running more than 10m
function smb_old_temp {
    (find monitor/ -mmin +5 -size +5c | grep -q temp_basal && echo temp_basal.json more than 5m old) \
    || ( jq --exit-status "(.duration-1) % 30 < 20" monitor/temp_basal.json >&4 \
        && echo -n "Temp basal set more than 10m ago: " && jq .duration monitor/temp_basal.json
        )
}

# make sure everything is in the right condition to SMB
function smb_check_everything {
    try_fail smb_reservoir_before
    try_fail smb_enact_temp
    if (grep -q '"units":' enact/smb-suggested.json 2>&3); then
        # wait_for_silence and retry if first attempt fails
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
        echo -n "No bolus needed. "
    fi
}

function smb_suggest {
    rm -rf enact/smb-suggested.json
    ls enact/smb-suggested.json 2>&3 >&4 && die "enact/suggested.json present"
    # Run determine-basal
    echo -n Temp refresh
    try_fail timerun openaps report invoke monitor/temp_basal.json monitor/clock.json monitor/clock-zoned.json 2>&3 >&4 | tail -1
    try_fail calculate_iob && echo ed
    try_fail determine_basal && cp -up enact/smb-suggested.json enact/suggested.json
    try_fail smb_verify_suggested
}

function determine_basal {
    timerun oref0-determine-basal monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json settings/autosens.json monitor/meal.json --microbolus --reservoir monitor/reservoir.json > enact/smb-suggested.json
}

# enact the appropriate temp before SMB'ing, (only if smb_verify_enacted fails or a 0 duration temp is requested)
function smb_enact_temp {
    smb_suggest
    if ( echo -n "enact/smb-suggested.json: " && cat enact/smb-suggested.json | jq -C -c . && grep -q duration enact/smb-suggested.json 2>&3 && ! smb_verify_enacted || jq --exit-status '.duration == 0' enact/smb-suggested.json >&4 ); then (
        rm enact/smb-enacted.json
        timerun openaps report invoke enact/smb-enacted.json 2>&3 >&4 | tail -1
        grep -q duration enact/smb-enacted.json || timerun openaps report invoke enact/smb-enacted.json 2>&3 >&4 | tail -1
        cp -up enact/smb-enacted.json enact/enacted.json
        echo -n "enact/smb-enacted.json: " && cat enact/smb-enacted.json | jq -C -c '. | "Rate: \(.rate) Duration: \(.duration)"'
        ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    else
        echo -n "No smb_enact needed. "
    fi
    ( smb_verify_enacted || ( smb_verify_status; smb_verify_enacted) )
}

function smb_verify_enacted {
    # Read the currently running temp and
    # verify rate matches (within 0.03U/hr) and duration is no shorter than 5m less than smb-suggested.json
    rm -rf monitor/temp_basal.json
    ( echo -n Temp refresh \
        && ( timerun openaps report invoke monitor/temp_basal.json || timerun openaps report invoke monitor/temp_basal.json ) \
        2>&3 >&4 | tail -1 && echo -n "ed: " \
    ) && echo -n "monitor/temp_basal.json: " && cat monitor/temp_basal.json | jq -C -c . \
    && jq --slurp --exit-status 'if .[1].rate then (.[0].rate > .[1].rate - 0.03 and .[0].rate < .[1].rate + 0.03 and .[0].duration > .[1].duration - 5 and .[0].duration < .[1].duration + 20) else true end' monitor/temp_basal.json enact/smb-suggested.json >&4
}

function smb_verify_reservoir {
    # Read the pump reservoir volume and verify it is within 0.1U of the expected volume
    rm -rf monitor/reservoir.json
    echo -n "Checking reservoir: " \
    && (timerun openaps report invoke monitor/reservoir.json || timerun openaps report invoke monitor/reservoir.json) 2>&3 >&4 | tail -1 \
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
    if grep incorrectly enact/smb-suggested.json 2>&3; then
        echo "Checking system clock against pump clock:"
        timerun oref0-set-system-clock 2>&3 >&4
    fi
    if jq -e -r .deliverAt enact/smb-suggested.json; then
        echo -n "Checking deliverAt: " && jq -r .deliverAt enact/smb-suggested.json | tr -d '\n' \
        && echo -n " is within 1m of current time: " && date \
        && (( $(bc <<< "$(date +%s -d $(jq -r .deliverAt enact/smb-suggested.json | tr -d '\n')) - $(date +%s)") > -60 )) \
        && (( $(bc <<< "$(date +%s -d $(jq -r .deliverAt enact/smb-suggested.json | tr -d '\n')) - $(date +%s)") < 60 )) \
        && echo "and that smb-suggested.json is less than 1m old" \
        && (find enact/ -mmin -1 -size +5c | grep -q smb-suggested.json)
    else
        echo No deliverAt found.
        cat enact/smb-suggested.json
        false
    fi
}

function smb_verify_status {
    # Read the pump status and verify it is not bolusing
    rm -rf monitor/status.json
    echo -n "Checking pump status (suspended/bolusing): "
    ( timerun openaps report invoke monitor/status.json || timerun openaps report invoke monitor/status.json ) 2>&3 >&4 | tail -1 \
    && cat monitor/status.json | jq -C -c . \
    && grep -q '"status": "normal"' monitor/status.json \
    && grep -q '"bolusing": false' monitor/status.json \
    && if grep -q '"suspended": true' monitor/status.json; then
        echo -n "Pump suspended; "
        unsuspend_if_no_temp
        refresh_pumphistory_and_meal
        false
    fi
}

function smb_bolus {
    # Verify that the suggested.json is less than 5 minutes old
    # and administer the supermicrobolus
    find enact/ -mmin -5 | grep smb-suggested.json >&4 \
    && if (grep -q '"units":' enact/smb-suggested.json 2>&3); then
        # press ESC three times on the pump to exit Bolus Wizard before SMBing, to help prevent A52 errors
        echo -n "Sending ESC ESC ESC to exit any open menus before SMBing: "
        try_return timerun openaps use pump press_keys esc esc esc | jq .completed | grep true \
        && try_return timerun openaps report invoke enact/bolused.json 2>&3 >&4 | tail -1 \
        && echo -n "enact/bolused.json: " && cat enact/bolused.json | jq -C -c . \
        && rm -rf enact/smb-suggested.json
    else
        echo -n "No bolus needed. "
    fi
}

function refresh_after_bolus_or_enact {
    if (find enact/ -mmin -2 -size +5c | grep -q bolused.json || (cat monitor/temp_basal.json | json -c "this.duration > 28" | grep -q duration)); then
        # refresh profile if >5m old to give SMB a chance to deliver
        refresh_profile 3
        refresh_pumphistory_and_meal \
            || ( wait_for_silence 15 && refresh_pumphistory_and_meal ) \
            || ( wait_for_silence 30 && refresh_pumphistory_and_meal )
        calculate_iob && determine_basal 2>&3 >&4 \
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
            timerun openaps use pump resume_pump
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
    if grep "MDT cgm" openaps.ini 2>&3 >&4; then
        echo \
        && echo Attempting to retrieve MDT CGM data from pump
        #due to sometimes the pump is not in a state to give this command repeat until it completes
        #"decocare.errors.DataTransferCorruptionError: Page size too short"
        n=0
        until [ $n -ge 3 ]; do
            timerun openaps report invoke monitor/cgm-mm-glucosedirty.json 2>&3 >&4 && break
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
        until timerun openaps report invoke monitor/cgm-mm-glucosedirty.json 2>&3 >&4; do
            echo cgm data from pump disrupted, retrying in 5 seconds...
            sleep 5;
            echo -n MDT cgm data retrieve
        done
    done
}
function mdt_get_bg {
    timerun openaps report invoke monitor/cgm-mm-glucosetrend.json 2>&3 >&4 \
    && timerun openaps report invoke cgm/cgm-glucose.json 2>&3 >&4 \
    && grep -q glucose cgm/cgm-glucose.json \
    && echo MDT CGM data retrieved \
    && cp -pu cgm/cgm-glucose.json cgm/glucose.json \
    && cp -pu cgm/glucose.json monitor/glucose-unzoned.json \
    && echo -n MDT New cgm data reformat \
    && timerun openaps report invoke monitor/glucose.json 2>&3 >&4 \
    && timerun openaps report invoke nightscout/glucose.json 2>&3 >&4 \
    && echo ted
}
# make sure we can talk to the pump and get a valid model number
function preflight {
    echo -n "Preflight "
    # only 515, 522, 523, 715, 722, 723, 554, and 754 pump models have been tested with SMB
    ( timerun openaps report invoke settings/model.json || timerun openaps report invoke settings/model.json ) 2>&3 >&4 | tail -1 \
    && ( egrep -q "[57](15|22|23|54)" settings/model.json || (grep 12 settings/model.json && die "error: x12 pumps do support SMB safety checks: quitting to restart with basal-only pump-loop") ) \
    && echo -n "OK. " \
    || ( echo -n "fail. "; false )
}

# reset radio, init world wide pump (if applicable), mmtune, and wait_for_silence 60 if no signal
function mmtune {
    # TODO: remove reset_spi_serial.py once oref0_init_pump_comms.py is fixed to do it correctly
    if [[ $port == "/dev/spidev5.1" ]]; then
        reset_spi_serial.py 2>&3
    fi
    oref0_init_pump_comms.py
    echo -n "Listening for 40s silence before mmtuning: "
    for i in $(seq 1 800); do
        echo -n .
        any_pump_comms 40 2>&3 | egrep -v subg | egrep -q No \
        && echo "No interfering pump comms detected from other rigs (this is a good thing!)" \
        && break
    done
    echo {} > monitor/mmtune.json
    echo -n "mmtune: " && timerun openaps report invoke monitor/mmtune.json 2>&3 >&4 | tail -1
    grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | while read line
        do echo -n "$line "
    done
    rssi_wait=$(grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | tail -1 | awk '($1 < -60) {print -($1+60)*2}')
    if [[ $rssi_wait > 1 ]]; then
        echo "waiting for $rssi_wait second silence before continuing"
        wait_for_silence $rssi_wait
        preflight
        echo "Done waiting for rigs with better signal."
    else
        echo "No wait required."
    fi
}

function maybe_mmtune {
    if ( find /tmp/ -mmin -15 | egrep -q "pump_loop_completed" ); then
        # mmtune ~ 25% of the time
        [[ $(( ( RANDOM % 100 ) )) > 75 ]] \
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
        && echo -n "Radio ok. " || { echo -n "Radio check failed. "; any_pump_comms 1 2>&1 | tail -1; mmtune; }
    echo -n "Listening: "
    for i in $(seq 1 800); do
        echo -n .
        any_pump_comms $waitfor 2>&3 | egrep -v subg | egrep -q No \
        && echo "No interfering pump comms detected from other rigs (this is a good thing!)" \
        && break
    done
}

# Refresh pumphistory etc.
function refresh_pumphistory_and_meal {
    retry_return timerun openaps report invoke monitor/status.json 2>&3 >&4 | tail -1 || return 1
    echo -n Ref
    ( grep -q "model.*12" monitor/status.json || \
         test $(cat monitor/status.json | json suspended) == true || \
         test $(cat monitor/status.json | json bolusing) == false ) \
         || { echo; cat monitor/status.json | jq -c -C .; return 1; }
    echo -n resh
    retry_return monitor_pump || return 1
    echo -n ed
    retry_return merge_pumphistory || return 1
    echo -n " pumphistory"
    retry_return timerun oref0-meal monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json || return 1
    echo " and meal.json"
}

# monitor-pump report invoke monitor/clock.json monitor/temp_basal.json monitor/pumphistory.json monitor/pumphistory-zoned.json monitor/clock-zoned.json monitor/iob.json monitor/reservoir.json monitor/battery.json monitor/status.json
function monitor_pump {
    retry_return invoke_pumphistory_etc || return 1
    retry_return invoke_reservoir_etc || return 1
}

function calculate_iob {
    timerun oref0-calculate-iob monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json settings/autosens.json > monitor/iob.json || { echo; echo "Couldn't calculate IOB"; fail "$@"; }
}

function invoke_pumphistory_etc {
    timerun openaps report invoke monitor/clock.json monitor/temp_basal.json monitor/pumphistory.json monitor/pumphistory-zoned.json monitor/clock-zoned.json 2>&3 >&4 | tail -1
    test ${PIPESTATUS[0]} -eq 0
}

function invoke_reservoir_etc {
    timerun openaps report invoke monitor/reservoir.json monitor/battery.json monitor/status.json 2>&3 >&4 | tail -1
    test ${PIPESTATUS[0]} -eq 0
}

function merge_pumphistory {
    jq -s '.[0] + .[1]|unique|sort_by(.timestamp)|reverse' monitor/pumphistory-zoned.json settings/pumphistory-24h-zoned.json > monitor/pumphistory-merged.json
    calculate_iob
}

# Calculate new suggested temp basal and enact it
function enact {
    rm enact/suggested.json
    timerun openaps report invoke enact/suggested.json \
    && if (cat enact/suggested.json && grep -q duration enact/suggested.json); then (
        rm enact/enacted.json
        timerun openaps report invoke enact/enacted.json 2>&3 >&4 | tail -1
        grep -q duration enact/enacted.json || timerun openaps report invoke enact/enacted.json ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    fi
    grep incorrectly enact/suggested.json && timerun oref0-set-system-clock 2>&3
    echo -n "enact/enacted.json: " && cat enact/enacted.json | jq -C -c .
}

# used by old pump-loop only
# refresh pumphistory if it's more than 15m old and enact
function refresh_old_pumphistory_enact {
    find monitor/ -mmin -15 -size +100c | grep -q pumphistory-zoned \
    || ( echo -n "Old pumphistory: " && refresh_pumphistory_and_meal && enact )
}

# refresh pumphistory if it's more than 30m old, but don't enact
function refresh_old_pumphistory {
    find monitor/ -mmin -30 -size +100c | grep -q pumphistory-zoned \
    || ( echo -n "Old pumphistory, waiting for $upto30s seconds of silence: " && wait_for_silence $upto30s && refresh_pumphistory_and_meal )
}

# refresh pumphistory_24h if it's more than 2h old
function refresh_old_pumphistory_24h {
    find settings/ -mmin -120 -size +100c | grep -q pumphistory-24h-zoned \
    || ( echo -n "Old pumphistory-24h, waiting for $upto30s seconds of silence: " && wait_for_silence $upto30s \
        && echo -n Old pumphistory-24h refresh \
        && timerun openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>&3 >&4 | tail -1 && echo ed )
}

# refresh settings/profile if it's more than 1h old
function refresh_old_profile {
    find settings/ -mmin -60 -size +5c | grep -q settings/profile.json && echo -n "Profile less than 60m old; " \
        || { echo -n "Old settings: " && get_settings; }
    if ls settings/profile.json >&4 && cat settings/profile.json | jq -e .current_basal >&3; then
        echo -n "Profile valid. "
    else
        echo -n "Profile invalid: "
        ls -lart settings/profile.json
        get_settings
    fi
}

# get-settings report invoke settings/model.json settings/bg_targets_raw.json settings/bg_targets.json settings/insulin_sensitivities_raw.json settings/insulin_sensitivities.json settings/basal_profile.json settings/settings.json settings/carb_ratios.json settings/pumpprofile.json settings/profile.json
function get_settings {
    if grep -q 12 settings/model.json
    then
        # If we have a 512 or 712, then remove the incompatible reports, so the loop will work
        # On the x12 pumps, these 'reports' are simulated by static json files created during the oref0-setup.sh run.
        NON_X12_ITEMS=""
    else
        # On all other supported pumps, these reports work. 
        NON_X12_ITEMS="settings/bg_targets_raw.json settings/bg_targets.json settings/basal_profile.json settings/settings.json"
    fi
    retry_return timerun openaps report invoke settings/model.json settings/insulin_sensitivities_raw.json settings/insulin_sensitivities.json settings/carb_ratios.json $NON_X12_ITEMS 2>&3 >&4 | tail -1 || return 1
    # generate settings/pumpprofile.json without autotune
    timerun oref0-get-profile settings/settings.json settings/bg_targets.json settings/insulin_sensitivities.json settings/basal_profile.json preferences.json settings/carb_ratios.json settings/temptargets.json --model=settings/model.json settings/autotune.json 2>&3 | jq . > settings/pumpprofile.json.new || { echo "Couldn't refresh pumpprofile"; fail "$@"; }
    if ls settings/pumpprofile.json.new >&4 && cat settings/pumpprofile.json.new | jq -e .current_basal >&4; then
        mv settings/pumpprofile.json.new settings/pumpprofile.json
        echo -n "Pump profile refreshed; "
    else
        echo "Invalid pumpprofile.json.new after refresh"
        ls -lart settings/pumpprofile.json.new
    fi
    # generate settings/profile.json.new with autotune
    timerun oref0-get-profile settings/settings.json settings/bg_targets.json settings/insulin_sensitivities.json settings/basal_profile.json preferences.json settings/carb_ratios.json settings/temptargets.json --model=settings/model.json --autotune settings/autotune.json | jq . > settings/profile.json.new || { echo "Couldn't refresh profile"; fail "$@"; }
    if ls settings/profile.json.new >&4 && cat settings/profile.json.new | jq -e .current_basal >&4; then
        mv settings/profile.json.new settings/profile.json
        echo -n "Settings refreshed; "
    else
        echo "Invalid profile.json.new after refresh"
        ls -lart settings/profile.json.new
    fi
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
    if ( (find monitor/ -newer monitor/temp_basal.json | grep -q glucose.json && echo -n "glucose.json newer than temp_basal.json. " ) \
        || (! find monitor/ -mmin -5 -size +5c | grep -q temp_basal && echo "temp_basal.json more than 5m old. ")); then
            echo -n Temp refresh
            retry_fail invoke_temp_etc
            echo ed
            timerun oref0-calculate-iob monitor/pumphistory-merged.json settings/profile.json monitor/clock-zoned.json settings/autosens.json || { echo "Couldn't calculate IOB"; fail "$@"; }
            if (cat monitor/temp_basal.json | json -c "this.duration < 27" | grep -q duration); then
                enact; else echo Temp duration 27m or more
            fi
    else
        echo -n "temp_basal.json less than 5m old. "
    fi
}

function invoke_temp_etc {
    timerun openaps report invoke monitor/temp_basal.json monitor/clock.json monitor/clock-zoned.json 2>&3 >&4 | tail -1
    test ${PIPESTATUS[0]} -eq 0
    calculate_iob
}

function refresh_pumphistory_and_enact {
    # set mtime of monitor/glucose.json to the time of its most recent glucose value
    setglucosetimestamp
    if ((find monitor/ -newer monitor/pumphistory-zoned.json | grep -q glucose.json && echo -n "glucose.json newer than pumphistory. ") \
        || (find enact/ -newer monitor/pumphistory-zoned.json | grep -q enacted.json && echo -n "enacted.json newer than pumphistory. ") \
        || ((! find monitor/ -mmin -5 | grep -q pumphistory-zoned || ! find monitor/ -mmin +0 | grep -q pumphistory-zoned) && echo -n "pumphistory more than 5m old. ") ); then
            { echo -n ": " && refresh_pumphistory_and_meal && enact; }
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
    || get_settings
}

function wait_for_bg {
    if grep "MDT cgm" openaps.ini 2>&3 >&4; then
        echo "MDT CGM configured; not waiting"
    elif egrep -q "Warning:" enact/smb-suggested.json 2>&3; then
        echo "Retrying without waiting for new BG"
    elif egrep -q "Waiting [0](\.[0-9])?m ([0-6]?[0-9]s )?to microbolus again." enact/smb-suggested.json 2>&3; then
        echo "Retrying microbolus without waiting for new BG"
    else
        echo -n "Waiting up to 4 minutes for new BG: "
        for i in `seq 1 24`; do
            if glucose-fresh; then
                break
            else
                echo -n .; sleep 10
            fi
        done
    fi
}

function glucose-fresh {
    # set mtime of monitor/glucose.json to the time of its most recent glucose value
    if jq  -e .[0].display_time monitor/glucose.json >/dev/null; then
        touch -d $(jq -r .[0].display_time monitor/glucose.json) monitor/glucose.json 2>&3
    else
        touch -d "$(date -R -d @$(jq .[0].date/1000 monitor/glucose.json))" monitor/glucose.json 2>&3
    fi
    if (! ls /tmp/pump_loop_completed >&4 ); then
        return 0;
    elif (find monitor/ -newer /tmp/pump_loop_completed | grep -q glucose.json); then
        echo glucose.json newer than pump_loop_completed
        return 0;
    else
        return 1;
    fi
}

function refresh_pumphistory_24h {
    if [ -e ~/src/EdisonVoltage/voltage ]; then
        sudo ~/src/EdisonVoltage/voltage json batteryVoltage battery > monitor/edison-battery.json 2>&3
    elif [ -e /root/src/openaps-menu/scripts/getvoltage.sh ]; then
        sudo /root/src/openaps-menu/scripts/getvoltage.sh > monitor/edison-battery.json 2>&3
    else
        rm monitor/edison-battery.json 2>&3
    fi
    if (! ls monitor/edison-battery.json 2>&3 >&4); then
        echo -n "Edison battery level not found. "
        autosens_freq=15
    elif (jq --exit-status ".battery >= 98 or (.battery <= 70 and .battery >= 60)" monitor/edison-battery.json >&4); then
        echo -n "Edison battery at $(jq .battery monitor/edison-battery.json)% is charged (>= 98%) or likely charging (60-70%). "
        autosens_freq=15
    elif (jq --exit-status ".battery < 98" monitor/edison-battery.json >&4); then
        echo -n "Edison on battery: $(jq .battery monitor/edison-battery.json)%. "
        autosens_freq=30
    else
        echo -n "Edison battery level unknown. "
        autosens_freq=15
    fi
    find settings/ -mmin -$autosens_freq -size +100c | grep -q pumphistory-24h-zoned && echo "Pumphistory-24 < ${autosens_freq}m old" \
    || { echo -n pumphistory-24h refresh \
        && timerun openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>&3 >&4 | tail -1 && echo ed; }
}

function setglucosetimestamp {
    if grep "MDT cgm" openaps.ini 2>&3 >&4; then
      touch -d "$(date -R -d @$(jq .[0].date/1000 nightscout/glucose.json))" monitor/glucose.json
    else
      touch -d "$(date -R -d @$(jq .[0].date/1000 monitor/glucose.json))" monitor/glucose.json
    fi
}

retry_fail() {
    "$@" || { echo Retrying $*; "$@"; } || { echo "Couldn't $*"; fail "$@"; }
}
retry_return() {
    "$@" || { echo Retrying $*; "$@"; } || { echo "Couldn't $* - continuing"; return 1; }
}
try_fail() {
    "$@" || { echo "Couldn't $*"; fail "$@"; }
}
try_return() {
    "$@" || { echo "Couldn't $*" - continuing; return 1; }
}
die() {
    echo "$@"
    exit 1
}

if grep 12 settings/model.json; then
    old_main "$@"
else
    main "$@"
fi
