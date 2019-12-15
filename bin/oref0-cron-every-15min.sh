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
    sudo ~/src/EdisonVoltage/voltage json batteryVoltage battery | jq .batteryVoltage | awk '{if ($1<=3050)system("sudo shutdown -h now")}' &
fi

# proper shutdown of pi rigs once the battery level is below 2 % (should be more than enough to shut down on a standard 18600 ~2Ah cell)
if is_pi; then
    sudo ~/src/openaps-menu/scripts/getvoltage.sh | tee ~/myopenaps/monitor/edison-battery.json | jq .battery | awk '{if ($1<2)system("sudo shutdown -h now")}' &
fi

# temporarily disable hotspot for 1m every 15m to allow it to try to connect via wifi again
(
    touch /tmp/disable_hotspot
    sleep 60
    rm /tmp/disable_hotspot
) &

oref0-version --check-for-updates > /tmp/oref0-updates.txt &
