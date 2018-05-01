#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Do all the things oref0 does once per minute, based on config files. This
should run from cron, in the myopenaps directory. Effects include trying to
get a network connection, killing crashed processes, syncing data, setting temp
basals, giving SMBs, and everything else that oref0 does. Writes to various
different log files, should (mostly) not write to stdout.
EOT

assert_cwd_contains_ini

CGM="$(get_pref_string .cgm)"
directory="$PWD"
CGM_LOOPDIR="$(get_pref_string .cgm_loop_path)"
ENABLE="$(get_pref_string .enable "")"
BT_PEB="$(get_pref_string .bt_peb "")"
BT_MAC="$(get_pref_string .bt_mac "")"
PUSHOVER_TOKEN="$(get_pref_string .pushover_token "")"
PUSHOVER_USER="$(get_pref_string .pushover_user "")"

function is_process_running_named ()
{
    if ps aux |grep -v grep |grep -q "$1"; then
        return 0
    else
        return 1
    fi
}
function is_bash_process_running_named ()
{
    if ps aux | grep -v grep | grep bash | grep -q "$1"; then
        return 0
    else
        return 1
    fi
}

if ! is_bash_process_running_named "oref0-online $BT_MAC"; then
    oref0-online "$BT_MAC" 2>&1 >> /var/log/openaps/network.log &
fi

sudo wpa_cli scan &

(
    killall -g --older-than 30m openaps
    killall -g --older-than 30m oref0-pump-loop
    killall -g --older-than 30m openaps-report
    killall -g --older-than 10m oref0-g4-loop
) &

# kill pump-loop after 5 minutes of not writing to pump-loop.log
find /var/log/openaps/pump-loop.log -mmin +5 | grep pump && (
    echo No updates to pump-loop.log in 5m - killing processes
    killall -g --older-than 5m openaps
    killall -g --older-than 5m oref0-pump-loop
    killall -g --older-than 5m openaps-report
) | tee -a /var/log/openaps/pump-loop.log &

if [[ ${CGM,,} =~ "g5-upload" ]]; then
    oref0-upload-entries &
fi

if [[ ${CGM,,} =~ "g4-go" ]]; then
        cd $CGM_LOOPDIR
        if ! is_bash_process_running_named oref0-g4-loop; then
            oref0-g4-loop | tee -a /var/log/openaps/cgm-loop.log &
        fi
# TODO: deprecate g4-upload and g4-local-only
elif [[ ${CGM,,} =~ "g4-upload" ]]; then
    (
        if ! is_process_running_named "oref0-monitor-cgm"; then
            (date; oref0-monitor-cgm) | tee -a /var/log/openaps/cgm-loop.log
        fi
        cp -up $CGM_LOOPDIR/monitor/glucose-raw-merge.json $directory/cgm/glucose.json
        cp -up $CGM_LOOPDIR/$directory/cgm/glucose.json $directory/monitor/glucose.json
    ) &
elif [[ ${CGM,,} =~ "xdrip" ]]; then
    if ! is_process_running_named "monitor-xdrip"; then
        monitor-xdrip | tee -a /var/log/openaps/xdrip-loop.log &
    fi
elif [[ $ENABLE =~ dexusb ]]; then
    true
elif ! [[ ${CGM,,} =~ "mdt" ]]; then # use nightscout for cgm
    if ! is_process_running_named "oref0-get-bg"; then
        (
            date
            oref0-get-bg
            cat cgm/glucose.json | jq -r  '.[] | \"\\(.sgv) \\(.dateString)\"' | head -1
        ) | tee -a /var/log/openaps/cgm-loop.log &
    fi
fi

if ! is_bash_process_running_named oref0-ns-loop; then
    oref0-ns-loop | tee -a /var/log/openaps/ns-loop.log &
fi

if ! is_bash_process_running_named oref0-autosens-loop; then
    oref0-autosens-loop 2>&1 | tee -a /var/log/openaps/autosens-loop.log &
fi

if ! is_bash_process_running_named oref0-pump-loop; then
    oref0-pump-loop 2>&1 | tee -a /var/log/openaps/pump-loop.log &
fi

if [[ ! -z "$BT_PEB" ]]; then
    if ! is_process_running_named "peb-urchin-status $BT_PEB"; then
        peb-urchin-status $BT_PEB 2>&1 | tee -a /var/log/openaps/urchin-loop.log &
    fi
fi

if [[ ! -z "$BT_PEB" || ! -z "$BT_MAC" ]]; then
    if ! is_bash_process_running_named oref0-bluetoothup; then
        oref0-bluetoothup >> /var/log/openaps/network.log &
    fi
fi

if [[ ! -z "$PUSHOVER_TOKEN" && ! -z "$PUSHOVER_USER" ]]; then
    oref0-pushover $PUSHOVER_TOKEN $PUSHOVER_USER 2>&1 >> /var/log/openaps/pushover.log &
fi
