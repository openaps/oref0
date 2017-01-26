#!/bin/bash

# main pump-loop
main() {
    prep
    until( \
        echo && echo Starting pump-loop at $(date): \
        && wait_for_silence \
        && refresh_old_pumphistory \
        && refresh_old_pumphistory_24h \
        && refresh_old_profile \
        && refresh_temp_and_enact \
        && refresh_pumphistory_and_enact \
        && refresh_profile \
        && refresh_pumphistory_24h \
        && echo Completed pump-loop at $(date) \
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
        echo && echo Starting supermicrobolus pump-loop at $(date) with $upto30s second wait_for_silence: \
        && wait_for_silence $upto30s \
        && preflight \
        && refresh_old_pumphistory_24h \
        && refresh_old_profile \
        && ( smb_check_everything \
            && smb_bolus \
            || ( smb_old_temp && ( \
                echo "Falling back to normal pump-loop" \
                && refresh_temp_and_enact \
                && refresh_pumphistory_and_enact \
                && refresh_profile \
                && refresh_pumphistory_24h \
                && echo Completed pump-loop at $(date) \
                && echo \
                ))
            ) \
            && refresh_profile \
            && refresh_pumphistory_24h \
            && echo Completed supermicrobolus pump-loop at $(date): \
            && echo \
    ); do
        echo Error, retrying && maybe_mmtune
        echo "Sleeping $upto10s; "
        sleep $upto10s
    done
}

function smb_reservoir_before {
    # Refresh reservoir.json and pumphistory.json
    gather \
    && cp monitor/reservoir.json monitor/lastreservoir.json \
    && echo -n "monitor/pumphistory.json: " && cat monitor/pumphistory.json | jq -C .[0]._description \
    && echo "Checking pump clock: " && cat monitor/clock-zoned.json \
    && echo "is within 2m of current time: " && date \
    && (( $(bc <<< "$(date +%s -d $(cat monitor/clock-zoned.json | sed 's/"//g')) - $(date +%s)") < 120 ))
}

function smb_old_temp {
    (find monitor/ -mmin +5 -size +5c | grep -q temp_basal && echo temp_basal.json more than 5m old) \
    || ( jq --exit-status "(.duration-1) % 30 < 20" monitor/temp_basal.json > /dev/null \
        && echo -n "Temp basal set more than 10m ago: " && jq .duration monitor/temp_basal.json
        )
}

function smb_check_everything {
    # wait_for_silence and retry if first attempt fails
    smb_reservoir_before \
    && smb_enact_temp \
    && smb_verify_enacted \
    && smb_verify_reservoir \
    && smb_verify_status \
    || ( echo Retrying SMB checks \
        && wait_for_silence 10 \
        && smb_reservoir_before \
        && smb_enact_temp \
        && smb_verify_enacted \
        && smb_verify_reservoir \
        && smb_verify_status
        )
}

function smb_enact_temp {
    rm -rf enact/smb-suggested.json
    ls enact/smb-suggested.json 2>/dev/null && die "enact/suggested.json present"
    # Run determine-basal
    # TODO: Add reports to oref0-setup:
    # openaps report add enact/smb-suggested.json JSON determine-basal shell monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json settings/autosens.json monitor/meal.json --microbolus --reservoir monitor/reservoir.json
    # openaps report add enact/smb-enacted.json JSON pump set_temp_basal enact/smb-suggested.json
    # openaps report add enact/bolused.json JSON pump bolus enact/smb-suggested.json
    echo -n Temp refresh && openaps report invoke monitor/temp_basal.json monitor/clock.json monitor/clock-zoned.json monitor/iob.json 2>&1 >/dev/null | tail -1 && echo ed \
    && openaps report invoke enact/smb-suggested.json \
    && cp -up enact/smb-suggested.json enact/suggested.json \
    && if (echo -n "enact/smb-suggested.json: " && cat enact/smb-suggested.json | jq -C -c . && grep -q duration enact/smb-suggested.json); then (
        rm enact/smb-enacted.json
        openaps report invoke enact/smb-enacted.json 2>&1 >/dev/null | tail -1
        grep -q duration enact/smb-enacted.json || openaps invoke enact/smb-enacted.json 2>&1 >/dev/null | tail -1
        cp -up enact/smb-enacted.json enact/enacted.json
        echo -n "enact/smb-enacted.json: " && cat enact/smb-enacted.json | jq -C -c .
        ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    fi
}

function smb_verify_enacted {
    # Read the currently running temp and
    # verify rate matches and duration is > 5m less than smb-suggested.json
    rm -rf monitor/temp_basal.json
    ( echo -n Temp refresh \
    && ( openaps report invoke monitor/temp_basal.json || openaps report invoke monitor/temp_basal.json ) \
        2>&1 >/dev/null | tail -1 && echo -n "ed: " \
    ) && echo -n "monitor/temp_basal.json: " && cat monitor/temp_basal.json | jq -C -c . \
    && jq --slurp --exit-status 'if .[1].rate then (.[0].rate == .[1].rate and .[0].duration > .[1].duration - 5) else true end' monitor/temp_basal.json enact/smb-suggested.json > /dev/null
    #&& jq --slurp --exit-status '.[1].rate, .[1].duration, .[0].rate, .[0].duration' monitor/temp_basal.json enact/smb-suggested.json \
    #) && grep '"rate": 0.0,' monitor/temp_basal.json
    #|| echo "WARNING: zero temp not running; continuing anyway"

}

function smb_verify_reservoir {
    # Read the pump reservoir volume and verify it is within 0.1U of the expected volume
    rm -rf monitor/reservoir.json
    echo -n "Checking reservoir: " \
    && (openaps invoke monitor/reservoir.json || openaps invoke monitor/reservoir.json) 2>&1 >/dev/null | tail -1 \
    && echo -n "reservoir level before: " \
    && cat monitor/lastreservoir.json \
    && echo -n " and after: " \
    && cat monitor/reservoir.json && echo \
    && (( $(bc <<< "$(< monitor/lastreservoir.json) - $(< monitor/reservoir.json) <= 0.1") ))
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
    # Verify that the suggested.json is less than 5 minutes old, and TODO: that the current time is prior to the timestamp by which the microbolus needs to be sent
    # Administer the supermicrobolus
    find enact/ -mmin -5 | grep smb-suggested.json \
    && if (grep -q '"units":' enact/smb-suggested.json); then
        openaps report invoke enact/bolused.json 2>&1 >/dev/null | tail -1 \
        && echo -n "enact/bolused.json: " && cat enact/bolused.json | jq -C -c . \
        && rm -rf enact/smb-suggested.json
    else
        echo "No bolus needed (yet)"
    fi
}

function prep {
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

function preflight {
    openaps report invoke settings/model.json 2>&1 >/dev/null | tail -1 \
    && egrep -q "[57][23]" settings/model.json \
    && echo -n "Preflight OK, "
}

function mmtune {
    reset_spi_serial.py 2>/dev/null
    echo {} > monitor/mmtune.json
    echo -n "mmtune: " && openaps report invoke monitor/mmtune.json 2>&1 >/dev/null | tail -1
    grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | while read line
        do echo -n "$line "
    done
}

function maybe_mmtune {
    # mmtune 8% of the time ((32k-30000)/32k)
    [[ $RANDOM > 30000 ]] \
    && echo "Waiting for 45s silence before mmtuning" \
    && wait_for_silence 45 \
    && mmtune
}

function wait_for_silence {
    if [ -z $1 ]; then
        waitfor=30
    else
        waitfor=$1
    fi
    ((mmeowlink-any-pump-comms.py --port $port --wait-for 1 | grep -q comms) 2>&1 | tail -1 && echo -n Radio ok, || mmtune) \
    && echo -n " Listening: "
    for i in $(seq 1 100); do
        echo -n .
        mmeowlink-any-pump-comms.py --port $port --wait-for $waitfor 2>/dev/null | egrep -v subg | egrep No \
        && break
    done
}

function gather {
    openaps report invoke monitor/status.json 2>&1 >/dev/null | tail -1 \
    && echo -n Ref \
    && test $(cat monitor/status.json | json bolusing) == false \
    && echo -n resh \
    && ( openaps monitor-pump || openaps monitor-pump ) 2>&1 | tail -1 \
    && echo ed pumphistory || (echo; exit 1) 2>/dev/null
}

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

function refresh_old_pumphistory {
    find monitor/ -mmin -15 -size +100c | grep -q pumphistory-zoned \
    || ( echo -n "Old pumphistory: " && gather && enact )
}

function refresh_old_pumphistory_24h {
    find settings/ -mmin -120 -size +100c | grep -q pumphistory-24h-zoned \
    || ( echo -n Old pumphistory-24h refresh \
        && openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>&1 >/dev/null | tail -1 && echo ed )
}

function refresh_old_profile {
    find settings/ -mmin -60 -size +5c | grep -q settings/profile.json && echo Profile less than 60m old \
    || (echo -n Old settings refresh && openaps get-settings 2>&1 >/dev/null | tail -1 && echo ed )
}

function refresh_temp_and_enact {
    if( (find monitor/ -newer monitor/temp_basal.json | grep -q glucose.json && echo glucose.json newer than temp_basal.json ) \
        || (! find monitor/ -mmin -5 -size +5c | grep -q temp_basal && echo temp_basal.json more than 5m old)); then
            (echo -n Temp refresh && openaps report invoke monitor/temp_basal.json monitor/clock.json monitor/clock-zoned.json monitor/iob.json 2>&1 >/dev/null | tail -1 && echo ed \
            && if (cat monitor/temp_basal.json | json -c "this.duration < 27" | grep -q duration); then
                enact; else echo Temp duration 27m or more
            fi)
    else
        echo temp_basal.json less than 5m old
    fi
}

function refresh_pumphistory_and_enact {
    if ((find monitor/ -newer monitor/pumphistory-zoned.json | grep -q glucose.json && echo -n glucose.json newer than pumphistory) \
        || (find enact/ -newer monitor/pumphistory-zoned.json | grep -q enacted.json && echo -n enacted.json newer than pumphistory) \
        || (! find monitor/ -mmin -5 | grep -q pumphistory-zoned && echo -n pumphistory more than 5m old) ); then
            (echo -n ": " && gather && enact )
    else
        echo Pumphistory less than 5m old
    fi
}

function refresh_profile {
    find settings/ -mmin -10 -size +5c | grep -q settings.json && echo Settings less than 10m old \
    || (echo -n Settings refresh && openaps get-settings 2>/dev/null >/dev/null && echo ed)
}

function refresh_pumphistory_24h {
    find settings/ -mmin -20 -size +100c | grep -q pumphistory-24h-zoned && echo Pumphistory-24 less than 20m old \
    || (echo -n pumphistory-24h refresh \
        && openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>&1 >/dev/null | tail -1 && echo ed)
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
