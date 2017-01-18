#!/bin/bash

# read tty port from pump.ini
eval $(grep port pump.ini | sed "s/ //g")
# if that fails, try the Explorer board default port
if [ -z $port ]; then
    port=/dev/spidev5.1
fi

function mmtune {
    reset_spi_serial.py 2>/dev/null
    echo {} > monitor/mmtune.json
    echo -n \"mmtune: \" && openaps report invoke monitor/mmtune.json 2>/dev/null >/dev/null
    grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | while read line
        do echo -n \"$line \"
    done
}

function wait_for_silence {
    if [ -z $1 ]; then
        waitfor=30
    else 
        waitfor=$1
    fi
    (mmeowlink-any-pump-comms.py --port $port --wait-for 1 | grep -q comms && echo -n Radio ok, || mmtune) \
    && echo -n \" Listening: \"
    for i in $(seq 1 100); do 
        echo -n .
        mmeowlink-any-pump-comms.py --port $port --wait-for $waitfor 2>/dev/null | egrep -v subg | egrep No \
        && break
    done
}

function gather {
    openaps report invoke monitor/status.json 2>/dev/null >/dev/null \
    && echo -n Ref \
    && test $(cat monitor/status.json | json bolusing) == false \
    && echo -n resh \
    && ( openaps monitor-pump || openaps monitor-pump ) 2>/dev/null >/dev/null \
    && echo ed pumphistory || (echo; exit 1) 2>/dev/null
}

function enact {
    rm enact/suggested.json
    openaps report invoke enact/suggested.json \
    && if (cat enact/suggested.json && grep -q duration enact/suggested.json); then ( 
        rm enact/enacted.json
        openaps report invoke enact/enacted.json
        grep -q duration enact/enacted.json || openaps invoke enact/enacted.json ) 2>&1 | egrep -v \"^  |subg_rfspy|handler\"
    fi
    grep incorrectly enact/suggested.json && oref0-set-system-clock 2>/dev/null
    cat enact/enacted.json | json -0
}

function refresh_old_pumphistory {
    find monitor/ -mmin -15 -size +100c | grep -q pumphistory-zoned \
    || ( echo -n \"Old pumphistory: \" && gather && enact ) 
}

function refresh_old_pumphistory_24h {
    find settings/ -mmin -120 -size +100c | grep -q pumphistory-24h-zoned \
    || ( echo -n Old pumphistory-24h refresh \
        && openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>/dev/null >/dev/null && echo ed )
}

function refresh_old_profile {
    find settings/ -mmin -60 -size +5c | grep -q settings/profile.json && echo Profile less than 60m old \
    || (echo -n Old settings refresh && openaps get-settings 2>/dev/null >/dev/null && echo ed )
}

function refresh_temp_and_enact {
    if( (find monitor/ -newer monitor/temp_basal.json | grep -q glucose.json && echo glucose.json newer than temp_basal.json ) \
        || (! find monitor/ -mmin -5 -size +5c | grep -q temp_basal && echo temp_basal.json more than 5m old)); then
            (echo -n Temp refresh && openaps report invoke monitor/temp_basal.json monitor/clock.json monitor/clock-zoned.json monitor/iob.json 2>/dev/null >/dev/null && echo ed \
            && if (cat monitor/temp_basal.json | json -c \"this.duration < 27\" | grep -q duration); then
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
            (echo -n \": \" && gather && enact )
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
        && openaps report invoke settings/pumphistory-24h.json settings/pumphistory-24h-zoned.json 2>/dev/null >/dev/null && echo ed)
}

sleep $[ ( $RANDOM / 2048 ) ]s
until( \
    echo Starting pump-loop at $(date): \
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

echo Error, retrying \
&& [[ $RANDOM > 30000 ]] \
&& wait_for_silence 45 \
&& mmtune
sleep 5
done
