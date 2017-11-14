#!/bin/bash
main() {
    echo
    echo Starting oref0-autosens-loop at $(date):
    overtemp && exit 1
    if highload && completed_recently; then
        echo Load high at $(date): waiting up to 30m to continue
        exit 2
    fi

    autosens 2>&1
    touch /tmp/autons-completed
    echo Completed oref0-autons-loop at $(date)
}

function overtemp {
    # check for CPU temperature above 85°C
    sensors -u 2>/dev/null | awk '$NF > 85' | grep input \
    && echo Edison is too hot: waiting for it to cool down at $(date)\
    && echo Please ensure rig is properly ventilated
}

function highload {
    # check whether system load average is high
    uptime | awk '$NF > 2' | grep load
}

function completed_recently {
    find /tmp/ -mmin -30 | egrep -q "autosens-completed"
}

# find settings/ -newer settings/autosens.json | grep -q pumphistory-24h-zoned.json || find settings/ -size -5c | grep -q autosens.json || ! find settings/ | grep -q autosens || ! find settings/autosens.json
# openaps use detect-sensitivity shell monitor/glucose.json settings/pumphistory-24h-zoned.json settings/insulin_sensitivities.json settings/basal_profile.json settings/profile.json monitor/carbhistory.json settings/temptargets.json
function autosens {
    # only run autosens if pumphistory-24h is newer than autosens
    if find settings/ -newer settings/autosens.json | grep -q pumphistory-24h-zoned.json \
        || find settings/ -size -5c | grep -q autosens.json \
        || ! find settings/ | grep -q autosens \
        || ! find settings/autosens.json >/dev/null; then
        if oref0-detect-sensitivity monitor/glucose.json settings/pumphistory-24h-zoned.json settings/insulin_sensitivities.json settings/basal_profile.json settings/profile.json monitor/carbhistory.json settings/temptargets.json > settings/autosens.json.new && cat settings/autosens.json.new | jq .ratio | grep -q [0-9]; then
            mv settings/autosens.json.new settings/autosens.json
            echo -n "Autosens refreshed: "
        else
            echo -n "Failed to refresh autosens: using old autosens.json: "
        fi
    else
        echo -n "No need to refresh autosens yet: "
    fi
    cat settings/autosens.json | jq . -C -c
}

die() {
    echo "$@"
    exit 1
}

main "$@"
