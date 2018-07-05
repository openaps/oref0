#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

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
export MEDTRONIC_PUMP_ID=`grep serial pump.ini | tr -cd 0-9`
export MEDTRONIC_FREQUENCY=`cat monitor/medtronic_frequency.ini`
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

usage "$@" <<EOT
Usage: $self
The main pump loop. Syncs with an insulin pump, enacts temporary basals and
SMB boluses. Normally runs from crontab.
EOT

# main pump-loop
main() {
    check_duty_cycle
    prep
    if ! overtemp; then
        echo && echo "Starting oref0-pump-loop at $(date) with $upto30s second wait_for_silence:"
        try_fail wait_for_bg
        try_fail wait_for_silence $upto30s
        retry_fail preflight
        try_fail if_mdt_get_bg
        # try_fail refresh_old_pumphistory
        try_fail refresh_old_profile
        try_fail touch /tmp/pump_loop_enacted -r monitor/glucose.json
        if retry_fail smb_check_everything; then
            if ( grep -q '"units":' enact/smb-suggested.json 2>&3); then
                if try_return smb_bolus; then
                    touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted
                    smb_verify_status
                else
                    echo "Bolus failed: retrying"
                    if retry_fail smb_check_everything; then
                        if ( grep -q '"units":' enact/smb-suggested.json 2>&3); then
                            if try_fail smb_bolus; then
                                touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted
                                smb_verify_status
                            fi
                        fi
                    fi
                fi
            fi
            touch /tmp/pump_loop_completed -r /tmp/pump_loop_enacted
            if ! glucose-fresh; then
                if onbattery; then
                    refresh_profile 30
                else
                    refresh_profile 15
                fi
                pumphistory_daily_refresh
                refresh_after_bolus_or_enact
            fi
            cat /tmp/oref0-updates.txt 2>&3
            touch /tmp/pump_loop_success
            echo Completed oref0-pump-loop at $(date)
            update_display
            echo
        else
            # pump-loop errored out for some reason
            fail "$@"
        fi
    fi
}

function update_display {
    # TODO: install this globally
    if [ -e /root/src/openaps-menu/scripts/status.js ]; then
        node /root/src/openaps-menu/scripts/status.js
    fi
}

function fail {
    echo -n "oref0-pump-loop failed. "
    if file_is_recent enact/smb-suggested.json && grep "too old" enact/smb-suggested.json >&4; then
        touch /tmp/pump_loop_completed
        wait_for_bg
        echo "Unsuccessful oref0-pump-loop (BG too old) at $(date)"
    # don't treat suspended pump as a complete failure
    elif file_is_recent monitor/status.json && grep -q '"suspended": true' monitor/status.json; then
        refresh_profile 15; pumphistory_daily_refresh
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
    update_display
    echo
    exit 1
}

# The function "check_duty_cycle" checks if the loop has to run and it returns 0 if so.
# It exits the script with code 0 otherwise.
# The desicion is based on the time since last *successful* loop.
# !Note duty cycle times are set in seconds.
#
# Additionally it may start an "emergency action" if enabled.
# Possible actions are usb power cycling or reboot the system.
# The EMERGENCY_ACTION variable sets the allowable time between successful loops.
# If no loop has completed in that time, it performs the enabled actions.
# !Note to enable a emergency action use 0 to enable and 1 to disable
#
# The intention is two fold:
# First the battery consumption is reduced (Pump and Pi) if the loop runs less often.
# This is most dramatic for Enlite CGM, where wait_for_bg can't be used.
# Secondly, if Carelink USB is used with Enlite, and wait_for_silence can't be used, this
# prevents the loop from disrupting the communication between the pump and enlite sensors.
#
# Use DUTY_CYCLE=0 (default) if you don't want to limit the loop
#
# Suggestion for Carelink USB users are
# DUTY_CYCLE=120
# EMERGENCY_ACTION=900
# REBOOT_ENABLE=0        #0=true
# USB_RESET_ENABLE=0    #0=true
#
# Default is DUTY_CYCLE=0 to disable this feature.
DUTY_CYCLE=${DUTY_CYCLE:-0}

EMERGENCY_ACTION=${EMERGENCY_ACTION:-900}
REBOOT_ENABLE=${REBOOT_ENABLE:-1}          #0=true
USB_RESET_ENABLE=${USB_RESET_ENABLE:-1}    #0=true

function check_duty_cycle {
    if [ "$DUTY_CYCLE" -gt "0" ]; then
        if [ -e /tmp/pump_loop_success ]; then
            DIFF_SECONDS=$(expr $(date +%s) - $(stat -c %Y /tmp/pump_loop_success))

            if ([ $USB_RESET_ENABLE ] || [ $REBOOT_ENABLE ]) && [ "$DIFF_SECONDS" -gt "$EMERGENCY_ACTION" ]; then
                if [ $USB_RESET_ENABLE ]; then
                    USB_RESET_DIFF=$EMERGENCY_ACTION
                    if [ -e /tmp/usp_power_cycled ]; then
                        USB_RESET_DIFF=$(expr $(date +%s) - $(stat -c %Y /tmp/usp_power_cycled))
                    fi

                    if [ "$USB_RESET_DIFF" -gt "$EMERGENCY_ACTION" ]; then
                        # file is old --> power-cycling is long time ago (most probably not this round) --> power-cycling
                        echo -n "$DIFF_SECONDS (of $DUTY_CYCLE) since last run --> trying to reset USB... "
                        /usr/local/bin/oref0-reset-usb 2>&3 >&4
                        touch /tmp/usp_power_cycled
                        echo " done. --> start new cycle."
                        return 0 #return to loop routine
                    fi
                fi
                # if usb reset doesn't help or is not enabled --> reboot system
                if [ $REBOOT_ENABLE ]; then
                    echo "$DIFF_SECONDS (of $DUTY_CYCLE) since last run --> rebooting."
                    sudo shutdown -r now
                    exit 0
                fi
            elif [ "$DIFF_SECONDS" -gt "$DUTY_CYCLE" ]; then
                echo "$DIFF_SECONDS (of $DUTY_CYCLE) since last run --> start new cycle."
                return 0
            else
                echo "$DIFF_SECONDS (of $DUTY_CYCLE) since last run --> stop now."
                exit 0
            fi
        else
            echo "/tmp/pump_loop_success does not exist; create it to start the loop duty cycle."
            # if pump_loop_success does not exist, use the system uptime
            touch -d "$(cat /proc/uptime | awk '{print $1}') seconds ago" /tmp/pump_loop_success
            return 0
        fi
    fi
}


function smb_reservoir_before {
    # Refresh reservoir.json and pumphistory.json
    retry_fail refresh_pumphistory_and_meal
    try_fail cp monitor/reservoir.json monitor/lastreservoir.json
    echo -n "Listening for $upto10s s silence: " && wait_for_silence $upto10s
    retry_fail check_clock
    echo -n "Checking that pump clock: "
    (cat monitor/clock-zoned.json; echo) | nonl
    echo -n " is within 90s of current time: " && date
    if (( $(bc <<< "$(to_epochtime $(cat monitor/clock-zoned.json)) - $(epochtime_now)") < -55 )) || (( $(bc <<< "$(to_epochtime $(cat monitor/clock-zoned.json)) - $(epochtime_now)") > 55 )); then
        echo Pump clock is more than 55s off: attempting to reset it and reload pumphistory
        oref0-set-device-clocks
        read_full_pumphistory
       fi
    (( $(bc <<< "$(to_epochtime $(cat monitor/clock-zoned.json)) - $(epochtime_now)") > -90 )) \
    && (( $(bc <<< "$(to_epochtime $(cat monitor/clock-zoned.json)) - $(epochtime_now)") < 90 )) || { echo "Error: pump clock refresh error / mismatch"; fail "$@"; }
    find monitor/ -mmin -5 -size +5c | grep -q pumphistory || { echo "Error: pumphistory-24h >5m old (or empty)"; fail "$@"; }
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
    retry_fail smb_enact_temp
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
    #changed the check below to report the error for the correct file...
    ls enact/smb-suggested.json 2>&3 >&4 && die "enact/smb-suggested.json present"
    # Run determine-basal
    echo -n Temp refresh
    retry_fail check_clock
    retry_fail check_tempbasal
    try_fail calculate_iob && echo -n "ed: "
    echo -n "monitor/temp_basal.json: " && cat monitor/temp_basal.json | colorize_json
    try_fail determine_basal && cp -up enact/smb-suggested.json enact/suggested.json
    try_fail smb_verify_suggested
}

function determine_basal {
    cat monitor/meal.json
    if ( grep -q 12 settings/model.json ); then
      oref0-determine-basal monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json settings/autosens.json monitor/meal.json --reservoir monitor/reservoir.json > enact/smb-suggested.json
    else
      oref0-determine-basal monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json settings/autosens.json monitor/meal.json --microbolus --reservoir monitor/reservoir.json > enact/smb-suggested.json
    fi
    cp -up enact/smb-suggested.json enact/suggested.json
}

# enact the appropriate temp before SMB'ing, (only if smb_verify_enacted fails or a 0 duration temp is requested)
function smb_enact_temp {
    smb_suggest
    echo -n "enact/smb-suggested.json: "
    cat enact/smb-suggested.json | colorize_json '. | del(.predBGs) | del(.reason)'
    cat enact/smb-suggested.json | colorize_json .reason
    if (jq --exit-status .predBGs.COB enact/smb-suggested.json >&4); then
        echo -n "COB: " && cat enact/smb-suggested.json |colorize_json .predBGs.COB
    fi
    if (jq --exit-status .predBGs.UAM enact/smb-suggested.json >&4); then
        echo -n "UAM: " && cat enact/smb-suggested.json |colorize_json .predBGs.UAM
    fi
    if (jq --exit-status .predBGs.IOB enact/smb-suggested.json >&4); then
        echo -n "IOB: " && cat enact/smb-suggested.json |colorize_json .predBGs.IOB
    fi
    if (jq --exit-status .predBGs.ZT enact/smb-suggested.json >&4); then
        echo -n "ZT:  " && cat enact/smb-suggested.json |colorize_json .predBGs.ZT
    fi
    if ( grep -q duration enact/smb-suggested.json 2>&3 && ! smb_verify_enacted || jq --exit-status '.duration == 0' enact/smb-suggested.json >&4 ); then (
        rm enact/smb-enacted.json
        ( mdt settempbasal enact/smb-suggested.json && jq '.  + {"received": true}' enact/smb-suggested.json > enact/smb-enacted.json ) 2>&3 >&4
        grep -q duration enact/smb-enacted.json || ( mdt settempbasal enact/smb-suggested.json && jq '.  + {"received": true}' enact/smb-suggested.json > enact/smb-enacted.json ) 2>&3 >&4
        cp -up enact/smb-enacted.json enact/enacted.json
        echo -n "enact/smb-enacted.json: " && cat enact/smb-enacted.json | colorize_json '. | "Rate: \(.rate) Duration: \(.duration)"'
        ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    else
        echo -n "No smb_enact needed. "
    fi
    try_fail smb_verify_status
    smb_verify_enacted
}

function smb_verify_enacted {
    # Read the currently running temp and
    # verify rate matches (within 0.03U/hr) and duration is no shorter than 5m less than smb-suggested.json
    rm -rf monitor/temp_basal.json
    ( echo -n Temp refresh \
        && ( check_tempbasal || check_tempbasal ) 2>&3 >&4 && echo -n "ed: " \
    ) && echo -n "monitor/temp_basal.json: " && cat monitor/temp_basal.json | colorize_json \
    && jq --slurp --exit-status 'if .[1].rate then (.[0].rate > .[1].rate - 0.03 and .[0].rate < .[1].rate + 0.03 and .[0].duration > .[1].duration - 5 and .[0].duration < .[1].duration + 20) else true end' monitor/temp_basal.json enact/smb-suggested.json >&4
}

function smb_verify_reservoir {
    # Read the pump reservoir volume and verify it is within 0.1U of the expected volume
    rm -rf monitor/reservoir.json
    echo -n "Checking reservoir: " \
    && ( check_reservoir || check_reservoir ) 2>&3 >&4 \
    && echo -n "reservoir level before: " \
    && cat monitor/lastreservoir.json | nonl \
    && echo -n ", suggested: " \
    && jq -r -C -c .reservoir enact/smb-suggested.json | nonl \
    && echo -n " and after: " \
    && cat monitor/reservoir.json \
    && (( $(bc <<< "$(< monitor/lastreservoir.json) - $(< monitor/reservoir.json) <= 0.1") )) \
    && (( $(bc <<< "$(< monitor/lastreservoir.json) - $(< monitor/reservoir.json) >= 0") )) \
    && (( $(bc <<< "$(jq -r .reservoir enact/smb-suggested.json | nonl) - $(< monitor/reservoir.json) <= 0.1") )) \
    && (( $(bc <<< "$(jq -r .reservoir enact/smb-suggested.json | nonl) - $(< monitor/reservoir.json) >= 0") ))
}

function smb_verify_suggested {
    if grep incorrectly enact/smb-suggested.json 2>&3; then
        echo "Checking system clock against pump clock:"
        oref0-set-system-clock 2>&3 >&4
    fi
    if grep "!= lastTemp rate" enact/smb-suggested.json; then
        echo Pumphistory/temp mismatch: retrying
        return 1
    fi
    if [ -s enact/smb-suggested.json ] && jq -e -r .deliverAt enact/smb-suggested.json; then
        echo -n "Checking deliverAt: " && jq -r .deliverAt enact/smb-suggested.json | nonl \
        && echo -n " is within 1m of current time: " && date \
        && (( $(bc <<< "$(to_epochtime $(jq -r .deliverAt enact/smb-suggested.json)) - $(epochtime_now)") > -60 )) \
        && (( $(bc <<< "$(to_epochtime $(jq -r .deliverAt enact/smb-suggested.json)) - $(epochtime_now)") < 60 )) \
        && echo "and that smb-suggested.json is less than 1m old" \
        && (file_is_recent_and_min_size enact/smb-suggested.json 1)
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
    ( check_status || check_status ) 2>&3 >&4 \
    && cat monitor/status.json | colorize_json \
    && grep -q '"status": "normal"' monitor/status.json \
    && grep -q '"bolusing": false' monitor/status.json \
    && if grep -q '"suspended": true' monitor/status.json; then
        echo -n "Pump suspended; "
        unsuspend_if_no_temp
        refresh_pumphistory_and_meal
        false
    fi \
    && if grep -q 12 monitor/status.json; then
    echo -n "x12 model detected."
        true
    fi
}

function smb_bolus {
    # Verify that the suggested.json is less than 5 minutes old
    # and administer the supermicrobolus
    #mdt bolus does not work on the 723 yet. Only tested on 722 pump
    file_is_recent enact/smb-suggested.json \
    && if (grep -q '"units":' enact/smb-suggested.json 2>&3); then
        # press ESC four times on the pump to exit Bolus Wizard before SMBing, to help prevent A52 errors
        echo -n "Sending ESC ESC ESC ESC to exit any open menus before SMBing "
        try_return mdt -f internal button esc esc esc esc 2>&3 \
        && echo -n "and bolusing " && jq .units enact/smb-suggested.json | nonl && echo " units" \
        && ( try_return mdt bolus enact/smb-suggested.json 2>&3 && jq '.  + {"received": true}' enact/smb-suggested.json > enact/bolused.json ) \
        && rm -rf enact/smb-suggested.json
    else
        echo -n "No bolus needed. "
    fi
}
# keeping this here in case mdt bolus command does not work, just swap the lines.
# && try_return openaps report invoke enact/bolused.json 2>&3 >&4 | tail -1 \

function refresh_after_bolus_or_enact {
    last_treatment_time=$(date -d $(cat monitor/pumphistory-24h-zoned.json | jq .[0].timestamp | noquotes))
    newer_enacted=$(find enact -newer monitor/pumphistory-24h-zoned.json -size +5c | egrep /enacted)
    newer_bolused=$(find enact -newer monitor/pumphistory-24h-zoned.json -size +5c | egrep /bolused)
    enacted_duration=$(grep duration enact/enacted.json)
    bolused_units=$(grep units enact/bolused.json)
    if [[ $newer_enacted && $enacted_duration ]] || [[ $newer_bolused && $bolused_units ]]; then
        echo -n "Refreshing pumphistory because: "
        if [[ $newer_enacted && $enacted_duration ]]; then
            echo -n "enacted, "
        fi
        if [[ $newer_bolused && $bolused_units ]]; then
            echo -n "bolused, "
        fi
        # refresh profile if >5m old to give SMB a chance to deliver
        refresh_profile 3
        refresh_pumphistory_and_meal || return 1
        # TODO: check that last pumphistory record is newer than last bolus and refresh again if not
        calculate_iob && determine_basal 2>&3 \
        && cp -up enact/smb-suggested.json enact/suggested.json \
        && echo -n "IOB: " && cat enact/smb-suggested.json | jq .IOB
        true
    fi

}

function unsuspend_if_no_temp {
    # If temp basal duration is zero, unsuspend pump
    if (cat monitor/temp_basal.json | json -c "this.duration == 0" | grep -q duration); then
        if check_pref_bool .unsuspend_if_no_temp false; then
            echo Temp basal has ended: unsuspending pump
            mdt resume 2>&3
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
    upto30s=$[ ( $RANDOM / 1092 + 1) ]
    upto45s=$[ ( $RANDOM / 728 + 1) ]
    # override random upto30s and upto45s waits with contents of /tmp/wait_for_silence if it exists (for multi-rig testing)
    if [ -f "/tmp/wait_for_silence" ]; then
        upto30s=$(head -1 /tmp/wait_for_silence)
        upto45s=$(head -1 /tmp/wait_for_silence)
    fi
    # read tty port from pump.ini
    eval $(grep port pump.ini | sed "s/ //g")
    # if that fails, try the Explorer board default port
    if [ -z $port ]; then
        port=/dev/spidev5.1
    fi

    # necessary to enable SPI communication over edison GPIO 110 on Edison + Explorer Board
    [ -f /sys/kernel/debug/gpio_debug/gpio110/current_pinmux ] && echo mode0 > /sys/kernel/debug/gpio_debug/gpio110/current_pinmux
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
            openaps report invoke monitor/cgm-mm-glucosedirty.json 2>&3 >&4 && break
            echo
            echo CGM data retrieval from pump disrupted, retrying in 5 seconds...
            n=$[$n+1]
            sleep 5;
            echo Reattempting to retrieve MDT CGM data
        done
        if [ -f "monitor/cgm-mm-glucosedirty.json" ]; then
            if [ -f "cgm/glucose.json" ]; then
                if [ $(to_epochtime $(jq .[1].date monitor/cgm-mm-glucosedirty.json)) == $(to_epochtime $(jq .[0].display_time monitor/glucose.json)) ]; then
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
    until [ $(to_epochtime @$(($(to_epochtime $(jq .[1].date monitor/cgm-mm-glucosedirty.json)) + 300))) -lt $(epochtime_now) ]; do
        CGMDIFFTIME=$(( $(to_epochtime @$(($(to_epochtime $(jq .[1].date monitor/cgm-mm-glucosedirty.json |noquotes)) + 300))) - $(epochtime_now) ))
        echo "Last CGM Time was $(date -d $(jq .[1].date monitor/cgm-mm-glucosedirty.json |noquotes) +"%r") wait untill $(date --date="@$(($(to_epochtime $(jq .[1].date monitor/cgm-mm-glucosedirty.json |noquotes)) + 300))" +"%r")to continue"
        echo "waiting for $CGMDIFFTIME seconds before continuing"
        sleep $CGMDIFFTIME
        until openaps report invoke monitor/cgm-mm-glucosedirty.json 2>&3 >&4; do
            echo cgm data from pump disrupted, retrying in 5 seconds...
            sleep 5;
            echo -n MDT cgm data retrieve
        done
    done
}
function mdt_get_bg {
    openaps report invoke monitor/cgm-mm-glucosetrend.json 2>&3 >&4 \
    && openaps report invoke cgm/cgm-glucose.json 2>&3 >&4 \
    && grep -q glucose cgm/cgm-glucose.json \
    && echo MDT CGM data retrieved \
    && cp -pu cgm/cgm-glucose.json cgm/glucose.json \
    && cp -pu cgm/glucose.json monitor/glucose-unzoned.json \
    && echo -n MDT New cgm data reformat \
    && openaps report invoke monitor/glucose.json 2>&3 >&4 \
    && openaps report invoke nightscout/glucose.json 2>&3 >&4 \
    && echo ted
}
# make sure we can talk to the pump and get a valid model number
function preflight {
    echo -n "Preflight "
    # only 515, 522, 523, 715, 722, 723, 554, and 754 pump models have been tested with SMB
    ( check_model || check_model ) 2>&3 >&4 \
    && ( egrep -q "[57](15|22|23|54)" settings/model.json || (grep -q 12 settings/model.json && echo -n "(x12 models do not support SMB safety checks, SMB will not be available.) ") ) \
    && echo -n "OK. " \
    || ( echo -n "fail. "; false )
}

# reset radio, init world wide pump (if applicable), mmtune, and wait_for_silence 60 if no signal
function mmtune {
    if grep "carelink" pump.ini 2>&1 >/dev/null; then
    echo "using carelink; skipping mmtune"
        return
    fi

    echo -n "Listening for $upto45s s silence before mmtuning: "
    wait_for_silence $upto45s

    echo {} > monitor/mmtune.json
    echo -n "mmtune: " && mmtune_Go >&3 2>&3
    # if mmtune.json is empty, re-run it and display output
    if ! [ -s monitor/mmtune.json ]; then
        mmtune_Go
    fi
    #Read and zero pad best frequency from mmtune, and store/set it so Go commands can use it,
    #but only if it's not the default frequency
    if ! $([ -s monitor/mmtune.json ] && jq -e .usedDefault monitor/mmtune.json); then
      freq=`jq -e .setFreq monitor/mmtune.json | tr -d "."`
      while [ ${#freq} -ne 9 ];
        do
         freq=$freq"0"
        done
      #Make sure we don't zero out the medtronic frequency. It will break everything.
      if [ $freq != "000000000" ] ; then
	   MEDTRONIC_FREQUENCY=$freq && echo $freq > monitor/medtronic_frequency.ini
      fi
    fi
    #Determine how long to wait, based on the RSSI value of the best frequency
    grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | while read line
        do echo -n "$line "
    done
    rssi_wait=$(grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | tail -1 | awk '($1 < -60) {print -($1+60)*2}')
    if [[ $rssi_wait -gt 1 ]]; then
        if [[ $rssi_wait -gt 90 ]]; then
            rssi_wait=90
        fi
        echo "waiting for $rssi_wait second silence before continuing"
        wait_for_silence $rssi_wait
        echo "Done waiting for rigs with better signal."
    else
        echo "No wait required."
    fi
}

function maybe_mmtune {
    if file_is_recent /tmp/pump_loop_completed 15; then
        # mmtune ~ 25% of the time
        [[ $(( ( RANDOM % 100 ) )) > 75 ]] \
        && mmtune
    else
        echo "pump_loop_completed more than 15m old; waiting for $upto45s s silence before mmtuning"
        update_display
        wait_for_silence $upto45s
        mmtune
    fi
}


# listen for $1 seconds of silence (no other rigs talking to pump) before continuing
function wait_for_silence {
    if grep "carelink" pump.ini 2>&1 >/dev/null; then
    echo "using carelink; not waiting for silence"
        return
    fi
    if [ -z $1 ]; then
        waitfor=$upto45s
    else
        waitfor=$1
    fi
    # check radio multiple times, and mmtune if all checks fail
    #disabling radio check because I can't figure this part out yet
#    ( ( out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
#      ( echo -n .; sleep 1; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
#      ( echo -n .; sleep 2; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
#      ( echo -n .; sleep 4; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) ) || \
#      ( echo -n .; sleep 8; out=$(any_pump_comms 1) ; echo $out | grep -qi comms || (echo $out; false) )
#    ) 2>&1 | tail -2 \
#        && echo -n "Radio ok. " || { echo -n "Radio check failed. "; any_pump_comms 1 2>&1 | tail -1; mmtune; }
    echo -n "Listening: "
    for i in $(seq 1 800); do
        echo -n .
        # returns true if it hears pump comms, false otherwise
        if ! listen -t $waitfor's' 2>&4 ; then
            echo "No interfering pump comms detected from other rigs (this is a good thing!)"
            echo -n "Continuing oref0-pump-loop at "; date
            break
        fi
    done
}

# Refresh pumphistory etc.
function refresh_pumphistory_and_meal {
    retry_return check_status 2>&3 >&4 || return 1
    ( grep -q 12 settings/model.json || \
         test $(cat monitor/status.json | json suspended) == true || \
         test $(cat monitor/status.json | json bolusing) == false ) \
         || { echo; cat monitor/status.json | colorize_json; return 1; }
    try_return invoke_pumphistory_etc || return 1
    try_return invoke_reservoir_etc || return 1
    echo -n "meal.json "
    if ! retry_return oref0-meal monitor/pumphistory-24h-zoned.json settings/profile.json monitor/clock-zoned.json monitor/glucose.json settings/basal_profile.json monitor/carbhistory.json > monitor/meal.json.new ; then
        echo; echo "Couldn't calculate COB"
        return 1
    fi
    try_return check_cp_meal || return 1
    echo -n "refreshed: "
    cat monitor/meal.json
}

function check_cp_meal {
    if ! [ -s monitor/meal.json.new ]; then
        echo meal.json.new not found
        return 1
    fi
    if grep "Could not parse input data" monitor/meal.json.new; then
        cat monitor/meal.json
        return 1
    fi
    if jq -e .carbs monitor/meal.json.new >&3; then
        cp monitor/meal.json.new monitor/meal.json
    else
        echo meal.json.new invalid
        return 1
    fi
}

function calculate_iob {
    oref0-calculate-iob monitor/pumphistory-24h-zoned.json settings/profile.json monitor/clock-zoned.json settings/autosens.json > monitor/iob.json.new || { echo; echo "Couldn't calculate IOB"; fail "$@"; }
    [ -s monitor/iob.json.new ] && jq -e .[0].iob monitor/iob.json.new >&3 && cp monitor/iob.json.new monitor/iob.json || { echo; echo "Couldn't copy IOB"; fail "$@"; }
}

function invoke_pumphistory_etc {
    check_clock 2>&3 >&4 || return 1
    read_pumphistory 2>&3  || return 1
    check_tempbasal 2>&3 >&4 || return 1
}

function invoke_reservoir_etc {
    check_reservoir 2>&3 >&4 || return 1
    check_status 2>&3 >&4 || return 1
    check_battery 2>&3 >&4 || return 1
}

# Calculate new suggested temp basal and enact it
function enact {
    rm enact/suggested.json
    determine_basal && if (cat enact/suggested.json && grep -q duration enact/suggested.json); then (
        rm enact/enacted.json
        ( mdt settempbasal enact/suggested.json && jq '.  + {"received": true}' enact/suggested.json > enact/enacted.json ) 2>&3 >&4
        grep -q duration enact/enacted.json || ( mdt settempbasal enact/suggested.json && jq '.  + {"received": true}' enact/suggested.json > enact/enacted.json ) ) 2>&1 | egrep -v "^  |subg_rfspy|handler"
    fi
    grep incorrectly enact/suggested.json && oref0-set-system-clock 2>&3
    echo -n "enact/enacted.json: " && cat enact/enacted.json | colorize_json
}

# refresh pumphistory_24h if it's more than 5m old
function refresh_old_pumphistory {
    (file_is_recent monitor/pumphistory-24h-zoned.json 5 100 \
     && echo -n "Pumphistory-24h less than 5m old. ") \
    || ( echo -n "Old pumphistory-24h, waiting for $upto30s seconds of silence: " && wait_for_silence $upto30s \
        && read_pumphistory )
}

# refresh settings/profile if it's more than 1h old
function refresh_old_profile {
    file_is_recent_and_min_size settings/profile.json 60 && echo -n "Profile less than 60m old; " \
        || { echo -n "Old settings: " && get_settings; }
    if [ -s settings/profile.json ] && jq -e .current_basal settings/profile.json >&3; then
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
        retry_return check_model 2>&3 >&4 || return 1
        retry_return read_insulin_sensitivities 2>&3 >&4 || return 1
        retry_return read_carb_ratios 2>&3 >&4 || return 1
        retry_return openaps report invoke settings/insulin_sensitivities.json settings/bg_targets.json 2>&3 >&4 || return 1
	#NON_X12_ITEMS=""
    else
        # On all other supported pumps, we should be able to get all the data we need from the pump.
        retry_return check_model 2>&3 >&4 || return 1
        retry_return read_insulin_sensitivities 2>&3 >&4 || return 1
        retry_return read_carb_ratios 2>&3 >&4 || return 1
        retry_return read_bg_targets 2>&3 >&4 || return 1
        retry_return read_basal_profile 2>&3 >&4 || return 1
        retry_return read_settings 2>&3 >&4 || return 1
        retry_return openaps report invoke settings/insulin_sensitivities.json settings/bg_targets.json 2>&3 >&4 || return 1
#        NON_X12_ITEMS="settings/bg_targets_raw.json settings/bg_targets.json settings/basal_profile.json settings/settings.json"
    fi
#    retry_return openaps report invoke settings/insulin_sensitivities_raw.json settings/insulin_sensitivities.json settings/carb_ratios.json $NON_X12_ITEMS 2>&3 >&4 | tail -1 || return 1

    # generate settings/pumpprofile.json without autotune
    oref0-get-profile settings/settings.json settings/bg_targets.json settings/insulin_sensitivities.json settings/basal_profile.json preferences.json settings/carb_ratios.json settings/temptargets.json --model=settings/model.json settings/autotune.json 2>&3 | jq . > settings/pumpprofile.json.new || { echo "Couldn't refresh pumpprofile"; fail "$@"; }
    if [ -s settings/pumpprofile.json.new ] && jq -e .current_basal settings/pumpprofile.json.new >&4; then
        mv settings/pumpprofile.json.new settings/pumpprofile.json
        echo -n "Pump profile refreshed; "
    else
        echo "Invalid pumpprofile.json.new after refresh"
        ls -lart settings/pumpprofile.json.new
    fi
    # generate settings/profile.json.new with autotune
    oref0-get-profile settings/settings.json settings/bg_targets.json settings/insulin_sensitivities.json settings/basal_profile.json preferences.json settings/carb_ratios.json settings/temptargets.json --model=settings/model.json --autotune settings/autotune.json | jq . > settings/profile.json.new || { echo "Couldn't refresh profile"; fail "$@"; }
    if [ -s settings/profile.json.new ] && jq -e .current_basal settings/profile.json.new >&4; then
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
        || (! file_is_recent_and_min_size monitor/temp_basal.json && echo "temp_basal.json more than 5m old. ")); then
            echo -n Temp refresh
            retry_fail invoke_temp_etc
            echo ed
            oref0-calculate-iob monitor/pumphistory-24h-zoned.json settings/profile.json monitor/clock-zoned.json settings/autosens.json || { echo "Couldn't calculate IOB"; fail "$@"; }
            if (cat monitor/temp_basal.json | json -c "this.duration < 27" | grep -q duration); then
                enact; else echo Temp duration 27m or more
            fi
    else
        echo -n "temp_basal.json less than 5m old. "
    fi
}

function invoke_temp_etc {
    check_clock 2>&3 >&4 || return 1
    check_tempbasal 2>&3 >&4 || return 1
    calculate_iob
}

function refresh_pumphistory_and_enact {
    # set mtime of monitor/glucose.json to the time of its most recent glucose value
    setglucosetimestamp
    if ((find monitor/ -newer monitor/pumphistory-24h-zoned.json | grep -q glucose.json && echo -n "glucose.json newer than pumphistory. ") \
        || (find enact/ -newer monitor/pumphistory-24h-zoned.json | grep -q enacted.json && echo -n "enacted.json newer than pumphistory. ") \
        || ((! file_is_recent monitor/pumphistory-zoned.json || ! find monitor/ -mmin +0 | grep -q pumphistory-zoned) && echo -n "pumphistory more than 5m old. ") ); then
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
    file_is_recent_and_min_size settings/settings.json $profileage && echo -n "Settings less than $profileage minutes old. " \
    || get_settings
}

function onbattery {
    # check whether battery level is < 90%
    if is_edison; then
        jq --exit-status ".battery < 90 and (.battery > 70 or .battery < 60)" monitor/edison-battery.json >&4
    else
        jq --exit-status ".battery < 90" monitor/edison-battery.json >&4
    fi
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
        echo
    fi
}

function glucose-fresh {
    # set mtime of monitor/glucose.json to the time of its most recent glucose value
    if jq  -e .[0].display_time monitor/glucose.json >/dev/null; then
        touch -d $(jq -r .[0].display_time monitor/glucose.json) monitor/glucose.json 2>&3
    else
        touch -d "$(date -R -d @$(jq .[0].date/1000 monitor/glucose.json))" monitor/glucose.json 2>&3
    fi
    if [[ ! -e /tmp/pump_loop_completed ]]; then
        echo "First loop: not waiting"
        return 0;
    elif (find monitor/ -newer /tmp/pump_loop_completed | grep -q glucose.json); then
        echo glucose.json newer than pump_loop_completed
        return 0;
    else
        return 1;
    fi
}

#function refresh_pumphistory {
    #read_pumphistory;
#}

function setglucosetimestamp {
    if grep "MDT cgm" openaps.ini 2>&3 >&4; then
      touch -d "$(date -R -d @$(jq .[0].date/1000 nightscout/glucose.json))" monitor/glucose.json
    else
      touch -d "$(date -R -d @$(jq .[0].date/1000 monitor/glucose.json))" monitor/glucose.json
    fi
}

#These are replacements for pump control functions which call ecc1's mdt and medtronic repositories
function check_reservoir() {
  set -o pipefail
  mdt reservoir 2>&3 | tee monitor/reservoir.json && nonl < monitor/reservoir.json \
    && egrep -q [0-9] monitor/reservoir.json
}
function check_model() {
  set -o pipefail
  mdt model 2>&3 | tee settings/model.json
}
function check_status() {
  set -o pipefail
  if ( grep 12 settings/model.json ); then
    touch monitor/status.json
  else
    mdt status 2>&3 | tee monitor/status.json 2>&3 >&4 && cat monitor/status.json | colorize_json .status
  fi
}
function mmtune_Go() {
  set -o pipefail
  if ( grep "WW" pump.ini ); then
    Go-mmtune -ww | tee monitor/mmtune.json
  else
    Go-mmtune | tee monitor/mmtune.json
  fi
}
function check_clock() {
  set -o pipefail
  mdt clock 2>&3 | tee monitor/clock-zoned.json >&4 && grep -q T monitor/clock-zoned.json
}
function check_battery() {
  set -o pipefail
  mdt battery 2>&3 | tee monitor/battery.json && cat monitor/battery.json | jq .voltage
}
function check_tempbasal() {
  set -o pipefail
  mdt tempbasal 2>&3 | tee monitor/temp_basal.json >&4 && cat monitor/temp_basal.json | jq .temp >&4 && cp monitor/temp_basal.json monitor/last_temp_basal.json
}

# clear and refresh the 24h pumphistory file approximatively every 6 hours.
# It queries 27h of data, full refresh when oldest data is greater than 33 hours old.
function pumphistory_daily_refresh() {
    lastRecordTimestamp=$(jq -r '.[-1].timestamp' monitor/pumphistory-24h-zoned.json 2>&3)
    dateCutoff=$(to_epochtime "33 hours ago")
    echo "Daily refresh if $lastRecordTimestamp < $dateCutoff " >&3
    if [[ -z "$lastRecordTimestamp" || "$lastRecordTimestamp" == *"null"* || $(to_epochtime $lastRecordTimestamp) -le $dateCutoff ]]; then
            echo -n "Pumphistory >33h long: " && read_full_pumphistory
    fi
}

function read_pumphistory() {
  set -o pipefail
  topRecordTimestamp=$(jq -r '.[0].timestamp' monitor/pumphistory-24h-zoned.json 2>&3)
  echo "Quering pump for history since: $topRecordTimestamp" >&3
  if [[ -z "$topRecordTimestamp" || "$topRecordTimestamp" == *"null"* ]]; then
    read_full_pumphistory
  else
    # FIXME: the following logic queries the pump for all records since the
    # timestamp of the top record in the existing history file.
    # This might miss some records if the pump clock has been moved forward.
    # A better approach might to get all reconds until that top record
    # has been found and matched exactly by it's base64 data or some other identifier
    # other than the timestamp.
    # The logic could be improved once the pumphistory command support this feature.
    echo -n "Pump history update"
    try_fail mv monitor/pumphistory-24h-zoned.json monitor/pumphistory-24h-zoned-old.json
    if ((pumphistory -s $topRecordTimestamp  2>&3 | jq -f openaps.jq 2>&3 ) && cat monitor/pumphistory-24h-zoned-old.json) | jq -s '.[0] + .[1]'  > monitor/pumphistory-24h-zoned.json; then
        try_fail rm monitor/pumphistory-24h-zoned-old.json
        echo -n "d through $(jq -r '.[0].timestamp' monitor/pumphistory-24h-zoned.json); "
    else
        try_fail mv monitor/pumphistory-24h-zoned-old.json monitor/pumphistory-24h-zoned.json
        echo " failed. Last record $(jq -r '.[0].timestamp' monitor/pumphistory-24h-zoned.json)"
        return 1
    fi
  fi
}
function read_full_pumphistory() {
  set -o pipefail
  rm monitor/pumphistory-24h-zoned.json
  echo -n "Full history refresh" \
  && ((( pumphistory -n 27 2>&3 | jq -f openaps.jq 2>&3 | tee monitor/pumphistory-24h-zoned.json 2>&3 >&4 ) \
      && echo -n ed) \
     || (echo " failed. "; return 1)) \
  && echo " through $(jq -r '.[0].timestamp' monitor/pumphistory-24h-zoned.json)"
}
function read_bg_targets() {
  set -o pipefail
  mdt targets 2>&3 | tee settings/bg_targets_raw.json && cat settings/bg_targets_raw.json | jq .units
}
function read_insulin_sensitivities() {
  set -o pipefail
  mdt sensitivities 2>&3 | tee settings/insulin_sensitivities_raw.json \
    && cat settings/insulin_sensitivities_raw.json | jq .units
}
function read_basal_profile() {
  set -o pipefail
  mdt basal 2>&3 | tee settings/basal_profile.json && cat settings/basal_profile.json | jq .[0].start
}
function read_settings() {
  set -o pipefail
  mdt settings 2>&3 | tee settings/settings.json && cat settings/settings.json | jq .maxBolus
}
function read_carb_ratios() {
  set -o pipefail
  mdt carbratios 2>&3 | tee settings/carb_ratios.json && cat settings/carb_ratios.json | jq .units
}

retry_fail() {
    "$@" || { echo Retry 1 of $*; "$@"; } \
    || { wait_for_silence $upto10s; echo Retry 2 of $*; "$@"; } \
    || { wait_for_silence $upto30s; echo Retry 3 of $*; "$@"; } \
    || { echo "Couldn't $*"; fail "$@"; }
}
retry_return() {
    "$@" || { echo Retry 1 of $*; "$@"; } \
    || { wait_for_silence $upto10s; echo Retry 2 of $*; "$@"; } \
    || { wait_for_silence $upto30s; echo Retry 3 of $*; "$@"; } \
    || { echo "Couldn't $* - continuing"; return 1; }
}
try_fail() {
    "$@" || { echo "Couldn't $*"; fail "$@"; }
}
try_return() {
    "$@" || { echo "Couldn't $*" - continuing; return 1; }
}

main "$@"
