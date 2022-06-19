#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Do all the things that oref0 does at 15-minute intervals. This should run from
cron, in the myopenaps directory.
EOT

assert_cwd_contains_ini

# proper shutdown once the EdisonVoltage very low (< 3050mV; 2950 is dead)
if is_edison; then
    BATTERY_VOLTAGE="$(sudo ~/src/EdisonVoltage/voltage json batteryVoltage battery | jq .batteryVoltage)"
    echo "Battery voltage is $BATTERY_VOLTAGE."
    BATTERY_CUTOFF=$(get_pref_float .edison_battery_shutdown_voltage 3050)
    if (( "$BATTERY_VOLTAGE" <= "$BATTERY_CUTOFF" )); then
        echo "Critically low battery! Shutting down."
        sudo shutdown -h now
    fi
fi

# proper shutdown of pi rigs once the battery level is below 2 % (should be more than enough to shut down on a standard 18600 ~2Ah cell)
if is_pi; then
    BATTERY_PERCENT="$(sudo ~/src/openaps-menu/scripts/getvoltage.sh | tee ~/myopenaps/monitor/edison-battery.json | jq .battery)"
    BATTERY_CUTOFF=$(get_pref_float .pi_battery_shutdown_percent 2)
    echo "Battery level is $BATTERY_PERCENT percent"
    if (( "$BATTERY_PERCENT" < "$BATTERY_CUTOFF" )); then
        echo "Critically low battery! Shutting down."
        sudo shutdown -h now
    fi
fi

# temporarily disable hotspot for 1m every 15m to allow it to try to connect via wifi again
(
    touch /tmp/disable_hotspot
    sleep 60
    rm /tmp/disable_hotspot
) &

oref0-version --check-for-updates > /tmp/oref0-updates.txt &
/root/src/oref0/bin/oref0-upgrade.sh
