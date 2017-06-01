#!/bin/bash

# main pump-loop
main() {
    prep
    until( \
        echo && echo Starting pump-loop at $(date): \
        && wait_for_bg \
        && wait_for_silence \
        && if_mdt_get_bg \
        && refresh_old_pumphistory_enact \
        && refresh_old_pumphistory_24h \
        && refresh_old_profile \
        && touch monitor/pump_loop_enacted -r monitor/glucose.json \
        && refresh_temp_and_enact \
        && refresh_pumphistory_and_enact \
        && refresh_profile \
        && refresh_pumphistory_24h \
        && echo Completed pump-loop at $(date) \
        && touch monitor/pump_loop_completed -r monitor/pump_loop_enacted \
        && echo); do

            # On a random subset of failures, wait 45s and mmtune
            echo Error, retrying \
            && maybe_mmtune
            sleep 5
    done
}

# main supermicrobolus loop
smb_main() {
    prep
    until ( \
        prep
        echo && echo Starting supermicrobolus pump-loop at $(date) with $upto30s second wait_for_silence: \
        && wait_for_bg \
        && wait_for_silence $upto30s \
        && preflight \
        && if_mdt_get_bg \
        && refresh_old_pumphistory \
        && refresh_old_pumphistory_24h \
        && refresh_old_profile \
        && touch monitor/pump_loop_enacted -r monitor/glucose.json \
        && refresh_smb_temp_and_enact \
        && ( smb_check_everything \
            && if (grep -q '"units":' enact/smb-suggested.json); then
                ( smb_bolus && \
                    touch monitor/pump_loop_completed -r monitor/pump_loop_enacted \
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
            && refresh_profile \
            && refresh_pumphistory_24h \
            && echo Completed supermicrobolus pump-loop at $(date): \
            && touch monitor/pump_loop_completed -r monitor/pump_loop_enacted \
            && echo \
    ); do
        if grep -q '"suspended": true' monitor/status.json; then
            echo -n "Pump suspended; "
            smb_verify_status
        else
            echo Error, retrying && maybe_mmtune
        fi
        echo "Sleeping $upto10s; "
        sleep $upto10s
    done
}

function smb_reservoir_before {
    # Refresh reservoir.json and pumphistory.json
    gather \
    && cp monitor/reservoir.json monitor/lastreservoir.json \
    && echo -n "pumphistory.json: " && cat monitor/pumphistory.json | jq -C .[0]._description \
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
        && smb_verify_reservoir \
        && smb_verify_status \
        || ( echo Retrying SMB checks \
            && wait_for_silence 10 \
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
    ls enact/smb-suggested.json 2>/dev/null && die "enact/suggested.json present"
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
        echo -n "enact/smb-enacted.json: " && cat enact/smb-enacted.json | jq -C -c .
        ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    else
        echo -n "No smb_enact needed. "
    fi \
    && smb_verify_enacted
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
    && grep -q '"suspended": false' monitor/status.json
}

function smb_bolus {
    # Verify that the suggested.json is less than 5 minutes old
    # and administer the supermicrobolus
    find enact/ -mmin -5 | grep smb-suggested.json \
    && if (grep -q '"units":' enact/smb-suggested.json); then
        openaps report invoke enact/bolused.json 2>&1 >/dev/null | tail -1 \
        && echo -n "enact/bolused.json: " && cat enact/bolused.json | jq -C -c . \
        && rm -rf enact/smb-suggested.json
    else
        echo "No bolus needed (yet)"
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
    if grep "MDT cgm" openaps.ini; then
        openaps get-bg
    fi
}
# make sure we can talk to the pump and get a valid model number
function preflight {
    # only 515, 522, 523, 715, 722, 723, 554, and 754 pump models have been tested with SMB
    openaps report invoke settings/model.json 2>&1 >/dev/null | tail -1 \
    && egrep -q "[57](15|22|23|54)" settings/model.json \
    && echo -n "Preflight OK. "
}

# reset radio, init world wide pump (if applicable), mmtune, and wait_for_silence 60 if no signal
function mmtune {
    # TODO: remove reset_spi_serial.py once oref0_init_pump_comms.py is fixed to do it correctly
    reset_spi_serial.py 2>/dev/null
    oref0_init_pump_comms.py
    echo -n "Listening for 30s silence before mmtuning: "
    for i in $(seq 1 800); do
        echo -n .
        mmeowlink-any-pump-comms.py --port $port --wait-for 30 2>/dev/null | egrep -v subg | egrep No \
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
    fi
}

function maybe_mmtune {
    # mmtune 20% of the time ((32k-26214)/32k)
    [[ $RANDOM > 26214 ]] \
    && echo "Waiting for 30s silence before mmtuning" \
    && wait_for_silence 30 \
    && mmtune
}

# listen for $1 seconds of silence (no other rigs talking to pump) before continuing
function wait_for_silence {
    if [ -z $1 ]; then
        waitfor=30
    else
        waitfor=$1
    fi
    ((mmeowlink-any-pump-comms.py --port $port --wait-for 1 | grep -q comms) 2>&1 | tail -1 && echo -n "Radio ok. " || mmtune) \
    && echo -n "Listening: "
    for i in $(seq 1 800); do
        echo -n .
        mmeowlink-any-pump-comms.py --port $port --wait-for $waitfor 2>/dev/null | egrep -v subg | egrep No \
        && break
    done
}

# Refresh pumphistory etc.
function gather {
    openaps report invoke monitor/status.json 2>&1 >/dev/null | tail -1 \
    && echo -n Ref \
    && test $(cat monitor/status.json | json bolusing) == false \
    && echo -n resh \
    && ( openaps monitor-pump || openaps monitor-pump ) 2>&1 >/dev/null | tail -1 \
    && echo ed pumphistory || (echo; exit 1) 2>/dev/null
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

# refresh pumphistory if it's more than 15m old, but don't enact
function refresh_old_pumphistory {
    find monitor/ -mmin -15 -size +100c | grep -q pumphistory-zoned \
    || ( echo -n "Old pumphistory, waiting for $upto30s seconds of silence: " && wait_for_silence $upto30s && gather )
}

# refresh pumphistory_24h if it's more than 2h old
function refresh_old_pumphistory_24h {
    find settings/ -mmin -120 -size +100c | grep -q pumphistory-24h-zoned \
    || ( echo -n Old pumphistory-24h refresh \
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
    if ( find monitor/ -newer monitor/pump_loop_completed | grep -q glucose.json ); then
        echo "glucose.json newer than pump_loop_completed. "
        smb_enact_temp
    elif ( find monitor/ -mmin -5 -size +5c | grep -q monitor/pump_loop_completed ); then
        echo "pump_loop_completed more than 5m ago. "
        smb_enact_temp
    else
        echo -n "pump_loop_completed less than 5m ago. "
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
        || (! find monitor/ -mmin -5 | grep -q pumphistory-zoned && echo -n "pumphistory more than 5m old. ") ); then
            (echo -n ": " && gather && enact )
    else
        echo Pumphistory less than 5m old
    fi
}

function refresh_profile {
    find settings/ -mmin -10 -size +5c | grep -q settings.json && echo Settings less than 10m old \
    || (echo -n Settings refresh && openaps get-settings 2>/dev/null >/dev/null && echo ed)
}

function low_battery_wait {
    if (! ls monitor/edison-battery.json 2>/dev/null >/dev/null); then
        echo Edison battery level not found
    elif (jq --exit-status ".battery >= 98 or (.battery <= 65 and .battery >= 60)" monitor/edison-battery.json > /dev/null); then
        echo "Edison battery at $(jq .battery monitor/edison-battery.json)% is charged (>= 98%) or likely charging (60-65%)"
    elif (jq --exit-status ".battery < 98" monitor/edison-battery.json > /dev/null); then
        echo -n "Edison on battery: $(jq .battery monitor/edison-battery.json)%; "
        wait_for_bg
    else
        echo Edison battery level unknown
    fi
}

function wait_for_bg {
    if grep "MDT cgm" openaps.ini; then
        echo "MDT CGM configured; not waiting"
    else
        echo -n "Waiting up to 4 minutes for new BG: "
        for i in `seq 1 24`; do
            # set mtime of monitor/glucose.json to the time of its most recent glucose value
            touch -d "$(date -R -d @$(jq .[0].date/1000 monitor/glucose.json))" monitor/glucose.json
            if (! ls monitor/pump_loop_completed >/dev/null ); then
                break
            elif (find monitor/ -newer monitor/pump_loop_completed | grep -q glucose.json); then
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
        autosens_freq=20
    elif (jq --exit-status ".battery >= 98 or (.battery <= 65 and .battery >= 60)" monitor/edison-battery.json > /dev/null); then
        echo -n "Edison battery at $(jq .battery monitor/edison-battery.json)% is charged (>= 98%) or likely charging (60-65%). "
        autosens_freq=20
    elif (jq --exit-status ".battery < 98" monitor/edison-battery.json > /dev/null); then
        echo -n "Edison on battery: $(jq .battery monitor/edison-battery.json)%. "
        autosens_freq=90
    else
        echo -n "Edison battery level unknown. "
        autosens_freq=20
    fi
    find settings/ -mmin -$autosens_freq -size +100c | grep -q pumphistory-24h-zoned && echo "Pumphistory-24 < ${autosens_freq}m old" \
    || (echo -n pumphistory-24h refresh \
        && openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>&1 >/dev/null | tail -1 && echo ed)
}

function setglucosetimestamp {
    if grep "MDT cgm" openaps.ini; then
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
