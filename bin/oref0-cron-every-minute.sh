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

ps aux | grep -v grep | grep bash | grep -q "oref0-online '$BT_MAC'" || oref0-online '$BT_MAC' 2>&1 >> /var/log/openaps/network.log &

sudo wpa_cli scan &

(
    killall -g --older-than 30m openaps
    killall -g --older-than 30m oref0-pump-loop
    killall -g --older-than 30m openaps-report
    killall -g --older-than 10m oref0-g4-loop
) &

# kill pump-loop after 5 minutes of not writing to pump-loop.log
find /var/log/openaps/pump-loop.log -mmin +5 | grep pump && ( echo No updates to pump-loop.log in 5m - killing processes; killall -g --older-than 5m openaps; killall -g --older-than 5m oref0-pump-loop; killall -g --older-than 5m openaps-report ) | tee -a /var/log/openaps/pump-loop.log &

if [[ ${CGM,,} =~ "g5-upload" ]]; then
    oref0-upload-entries &
fi

if [[ ${CGM,,} =~ "g4-go" ]]; then
        cd $CGM_LOOPDIR
        ps aux | grep -v grep | grep bash | grep -q 'oref0-g4-loop' || oref0-g4-loop | tee -a /var/log/openaps/cgm-loop.log
# TODO: deprecate g4-upload and g4-local-only
elif [[ ${CGM,,} =~ "g4-upload" ]]; then
    (
        cd $CGM_LOOPDIR
        ps aux | grep -v grep | grep -q 'openaps monitor-cgm' || (date; openaps monitor-cgm) | tee -a /var/log/openaps/cgm-loop.log
        cp -up monitor/glucose-raw-merge.json $directory/cgm/glucose.json
        cp -up $directory/cgm/glucose.json $directory/monitor/glucose.json
    ) &
elif [[ ${CGM,,} =~ "xdrip" ]]; then
    ps aux | grep -v grep | grep -q 'monitor-xdrip' || monitor-xdrip | tee -a /var/log/openaps/xdrip-loop.log &
elif [[ $ENABLE =~ dexusb ]]; then
    true
elif ! [[ ${CGM,,} =~ "mdt" ]]; then # use nightscout for cgm
    ps aux | grep -v grep | grep -q 'openaps get-bg' || ( date; openaps get-bg ; cat cgm/glucose.json | jq -r  '.[] | \"\\(.sgv) \\(.dateString)\"' | head -1 ) | tee -a /var/log/openaps/cgm-loop.log &
fi

ps aux | grep -v grep | grep bash | grep -q 'oref0-ns-loop' || oref0-ns-loop | tee -a /var/log/openaps/ns-loop.log &

ps aux | grep -v grep | grep bash | grep -q 'oref0-autosens-loop' || oref0-autosens-loop 2>&1 | tee -a /var/log/openaps/autosens-loop.log &

( ps aux | grep -v grep | grep bash | grep bash | grep -q 'bin/oref0-pump-loop' || oref0-pump-loop ) 2>&1 | tee -a /var/log/openaps/pump-loop.log &

if [[ ! -z "$BT_PEB" ]]; then
    ( ps aux | grep -v grep | grep -q 'peb-urchin-status $BT_PEB' || peb-urchin-status $BT_PEB ) 2>&1 | tee -a /var/log/openaps/urchin-loop.log &
fi

if [[ ! -z "$BT_PEB" || ! -z "$BT_MAC" ]]; then
    ps aux | grep -v grep | grep bash | grep -q "oref0-bluetoothup" || oref0-bluetoothup >> /var/log/openaps/network.log &
fi

if [[ ! -z "$PUSHOVER_TOKEN" && ! -z "$PUSHOVER_USER" ]]; then
    oref0-pushover $PUSHOVER_TOKEN $PUSHOVER_USER 2>&1 >> /var/log/openaps/pushover.log &
fi
