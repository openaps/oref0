#!/bin/bash

# There are 3 known conditions in which communication between rig and pump is not working and a reboot is required.
# 1) spidev5.1 already in use, see https://github.com/openaps/oref0/pull/411
# 2) mmeowlink.exceptions.CommsException, see https://github.com/oskarpearson/mmeowlink/issues/60
# 3) hanging reset.py, see https://github.com/oskarpearson/mmeowlink/issues/60
# If one of those occur we will reboot the rig
# If it will restore within 5 minutes, than the reboot will be cancelled
# Note that this is a workaround, until we found the root cause of why the rig pump communication fails
# Note that there is one known false positive for the second issue. It will reboot if the port/device and/or radio_type have been misconfigured

radio_errors=`tail --lines=20 /var/log/openaps/pump-loop.log | egrep "spidev5.1 already in use|mmeowlink.exceptions.CommsException: Could not get subg_rfspy state or version|retry 0|TimeoutExpired. Killing process"`
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
