#!/bin/bash

GLUCOSE=$1

OLD=${2-5}
MAX_WAIT=${3-1}
TIME_SINCE=$(oref0-dex-time-since $GLUCOSE)
OLD_LSUSB=16.0


if (( $(bc <<< "$TIME_SINCE >= $OLD") )); then
  echo "CGM Data $TIME_SINCE mins ago is old (>=$OLD), not waiting"
  
  # if there is no CGM for more than OLD_LSUSB minutes (default 16)
  # and the lsusb is failing (e.g. unable to initialize libusb: -99
  # and there was no CGM update before the rig was up
  # reboot the system to restore the USB subsystem
  # this will make the CGM connected to the USB OTG work again
  if (( $(bc <<< "$TIME_SINCE >= $OLD_LSUSB") )); then
     if ! lsusb > /dev/null ; then
        echo "CGM Data $TIME_SINCE mins ago is old (>=$OLD) and lsusb returns error: "
        lsusb
        UPTIME_IN_MINUTES=$(awk '{ print $0/60 }' /proc/uptime)
        if (( $(bc <<< "$UPTIME_IN_MINUTES >= $TIME_SINCE") )); then
           shutdown -r now "lsusb error. Rebooting to restore USB subsystem"
        else  
           echo "Not rebooting again, because  CGM is updated $TIME_SINCE and rebooted $UPTIME_IN_MINUTES ago"
        fi
     fi
  fi
else
  WAIT_MINS=$(bc <<< "$OLD - $TIME_SINCE")
  if (( $(bc <<< "$WAIT_MINS >= $MAX_WAIT") )); then
    echo "CGM Data $TIME_SINCE mins ago is fresh (< $OLD), $WAIT_MINS mins > max wait ($MAX_WAIT mins) waiting for next attempt"
    exit 1
  else
    echo "CGM Data $TIME_SINCE mins ago is fresh (< $OLD), waiting $WAIT_MINS mins for new data"
    sleep ${WAIT_MINS}m
    echo "finished waiting, let's get some CGM Data"
  fi
fi

