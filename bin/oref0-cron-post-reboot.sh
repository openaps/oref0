#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Do all the things that oref0 does once per reboot, based on config files. This
should run from cron, in the myopenaps directory.
EOT

assert_cwd_contains_ini

CGM="$(get_pref_string .cgm)"
XDRIP_PATH="$(get_pref_string .xdrip_path)"
ttyport="$(get_pref_string .ttyport)"

if [[ "${CGM,,}" =~ "xdrip" ]]; then
    python "$XDRIP_PATH/xDripAPS.py" &
fi

# Get time from pump for offline looping in case a rig was down for a while
# At some point the rig will come online again and calibrates the local clock 
# and the clock of the pump
export MEDTRONIC_PUMP_ID=`get_pref_string .pump_serial | tr -cd 0-9`
export MEDTRONIC_FREQUENCY=`cat monitor/medtronic_frequency.ini`

sudo wpa_cli -i wlan0 scan
sleep 60 # wait for wifi to connect

if ! ifconfig | grep wlan0 -A 1 | grep -q inet ; then
  echo "$(date) -- Not online, getting clock from pump with $MEDTRONIC_PUMP_ID and $MEDTRONIC_FREQUENCY " >> /var/log/openaps/clock.log
  date -s $(mdt clock | sed 's/"//g')
  while [ $? -ne 0 ]; do 
    echo "$(date) -- FAILED. Trying again" >> /var/log/openaps/clock.log
    sleep 15
    date -s $(mdt clock | sed 's/"//g')
  done
  echo "$(date) -- SUCCESS" >> /var/log/openaps/clock.log
fi
# END CLOCK

oref0-delete-future-entries &

(
    cd ~/src/oref0/www
    export FLASK_APP=app.py
    flask run -p 80 --host=0.0.0.0 | tee -a /var/log/openaps/flask.log
) &
