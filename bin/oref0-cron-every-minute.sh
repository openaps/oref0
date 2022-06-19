#!/usr/bin/env bash

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

sudo wpa_cli -i wlan0 scan &

(
    killall -g --older-than 30m openaps
    killall-g oref0-pump-loop 1800
    killall -g --older-than 30m openaps-report
    killall-g oref0-g4-loop 600
    killall-g oref0-ns-loop 600
) &

# kill pump-loop after 5 minutes of not writing to pump-loop.log
find /var/log/openaps/pump-loop.log -mmin +5 | grep pump && (
    echo No updates to pump-loop.log in 5m - killing processes
    killall -g --older-than 5m openaps
    killall-g oref0-pump-loop 300
    killall -g --older-than 5m openaps-report
) | tee -a /var/log/openaps/pump-loop.log | adddate openaps.pump-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &

# if the rig doesn't recover after that, reboot:
oref0-radio-reboot &

if [[ ${CGM,,} =~ "g4-go" ]]; then
        cd $CGM_LOOPDIR
        if ! is_bash_process_running_named oref0-g4-loop; then
            oref0-g4-loop | tee -a /var/log/openaps/cgm-loop.log | adddate openaps.cgm-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &
        fi
        cd -
# TODO: deprecate g4-upload and g4-local-only
elif [[ ${CGM,,} =~ "g4-upload" ]]; then
    (
        if ! is_process_running_named "oref0-monitor-cgm"; then
            (date; oref0-monitor-cgm) | tee -a /var/log/openaps/cgm-loop.log | adddate openaps.cgm-loop | uncolor |tee -a /var/log/openaps/openaps-date.log
        fi
        cp -up $CGM_LOOPDIR/monitor/glucose-raw-merge.json $directory/cgm/glucose.json
        cp -up $CGM_LOOPDIR/$directory/cgm/glucose.json $directory/monitor/glucose.json
    ) &
elif [[ ${CGM,,} =~ "g5" || ${CGM,,} =~ "g5-upload" || ${CGM,,} =~ "g6" || ${CGM,,} =~ "g6-upload" ]]; then
    if ! is_process_running_named "oref0-monitor-cgm"; then
        (date; oref0-monitor-cgm) | tee -a /var/log/openaps/cgm-loop.log
    fi
elif [[ ${CGM,,} =~ "xdrip" ]]; then
    if ! is_process_running_named "monitor-xdrip"; then
        monitor-xdrip | tee -a /var/log/openaps/xdrip-loop.log | adddate openaps.xdrip-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &
    fi
elif ! [[ ${CGM,,} =~ "mdt" ]]; then # use nightscout for cgm
    if ! is_process_running_named "oref0-get-bg"; then
        (
            date
            oref0-get-bg
            cat cgm/glucose.json | jq -r  '.[] | \"\\(.sgv) \\(.dateString)\"' | head -1
        ) | tee -a /var/log/openaps/cgm-loop.log | adddate openaps.cgm-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &
    fi
fi

if [[ ${CGM,,} =~ "g5-upload" || ${CGM,,} =~ "g6-upload" ]]; then
    oref0-upload-entries &
fi

if ! is_bash_process_running_named oref0-ns-loop; then
    oref0-ns-loop | tee -a /var/log/openaps/ns-loop.log | adddate openaps.ns-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &
fi

if ! is_bash_process_running_named oref0-autosens-loop; then
    oref0-autosens-loop 2>&1 | tee -a /var/log/openaps/autosens-loop.log | adddate openaps.autosens-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &
fi

if ! is_bash_process_running_named oref0-pump-loop; then
    oref0-pump-loop 2>&1 | tee -a /var/log/openaps/pump-loop.log | adddate openaps.pump-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &
fi

if ! is_bash_process_running_named oref0-shared-node-loop; then
    oref0-shared-node-loop 2>&1 | tee -a /var/log/openaps/shared-node.log | adddate openaps.shared-node | uncolor |tee -a /var/log/openaps/openaps-date.log &
fi

if [[ ! -z "$BT_PEB" ]]; then
    if ! is_process_running_named "peb-urchin-status $BT_PEB"; then
        peb-urchin-status $BT_PEB 2>&1 | tee -a /var/log/openaps/urchin-loop.log | adddate openaps.urchin-loop | uncolor |tee -a /var/log/openaps/openaps-date.log &
    fi
fi

if [[ ! -z "$BT_PEB" || ! -z "$BT_MAC" ]]; then
    if ! is_bash_process_running_named oref0-bluetoothup; then
        oref0-bluetoothup >> /var/log/openaps/network.log &
    fi
fi

if [[ ! -z "$PUSHOVER_TOKEN" && ! -z "$PUSHOVER_USER" ]]; then
    #oref0-pushover $PUSHOVER_TOKEN $PUSHOVER_USER 2>&1 >> /var/log/openaps/pushover.log &
fi

# if disk has less than 10MB free, delete something and logrotate
cd /var/log/openaps/ && df . | awk '($4 < 10000) {print $4}' | while read line; do
    # find the oldest log file
    ls -t | tail -1
done | while read file; do
    # delete the oldest log file
    rm $file
    # attempt a logrotate
    logrotate /etc/logrotate.conf -f
done
start_share_node_if_needed

# check if 5 minutes have passed, and if yes, turn of the screen to save power
ttyport="$(get_pref_string .ttyport)"
upSeconds="$(cat /proc/uptime | grep -o '^[0-9]\+')"
upMins=$((${upSeconds} / 60))

if [[ "${upMins}" -gt "5" && "$ttyport" =~ spidev0.[01] ]]; then
    # disable HDMI on Explorer HAT rigs to save battery
    /usr/bin/tvservice -o &
fi
