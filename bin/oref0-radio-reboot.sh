#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self
Check the pump-loop logfile for certain types of radio errors. If any are
found, schedule a reboot to fix them. Otherwise cancel a pending reboot.
EOF

# There are 2 known conditions in which communication between rig and pump is not working and a reboot is required.
# 1) spidev5.1 already in use, see https://github.com/openaps/oref0/pull/411 (all pumps)
# 2) continuous 'retry 0' or hanging reset.py, see https://github.com/oskarpearson/mmeowlink/issues/60 (WW-pump users only)
# If one of those occur we will reboot the rig
# If it will restore within 5 minutes, then the reboot will be cancelled
# Note that this is a workaround, until we found the root cause of why the rig pump communication fails

SYSTEM_UP=$(date --date="$(uptime -s)" +%s)
# Start checking only when the system has been up for some time.
START_CHECKING=$(date -d"30 minutes ago" +%s)
if [ $SYSTEM_UP -lt $START_CHECKING ]; then
  radio_errors=`tail --lines=20 /var/log/openaps/pump-loop.log | egrep "spidev.* in use|retry 0|illing process"`
  logfile=/var/log/openaps/pump-loop.log
  if [ ! -z "$radio_errors" ]; then
      if [ ! -e /run/nologin ]; then
          echo >> $logfile
          echo -n "Radio error found at " | tee -a $logfile
          date >> $logfile
          shutdown -r +5 "Rebooting to fix radio errors!" | tee -a $logfile
          echo >> $logfile
      fi
  else
      if [ -e /run/nologin ]; then
          echo "No more radio errors; canceling reboot" | tee -a $logfile
          shutdown -c | tee -a $logfile
      fi
  fi
fi
