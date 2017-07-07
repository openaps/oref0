#!/bin/bash

GLUCOSE=$1

OLD=${2-5}
TIME_SINCE=$(oref0-dex-time-since $GLUCOSE)
OLD_LSUSB=16.0

if (( $(bc <<< "$TIME_SINCE >= $OLD") )); then
  echo "CGM Data $TIME_SINCE mins ago is old (>=$OLD)"
 
  # if there is no CGM for more than OLD_LSUSB minutes
  # and uptime is more than 30 minutes
  # reboot the system to restore the USB subsystem and the CGM
  # that is connected to USB OTG
  if (( $(bc <<< "$TIME_SINCE >= $OLD_LSUSB") )); then
     if ! lsusb > /dev/null ; then
        echo "CGM Data $TIME_SINCE mins ago is old (>=$OLD_LSUSB) and lsusb returns error: "
        lsusb
        if ! awk '{print "Uptime: ", $0/60, " minutes"; if ($0/60 > 30) exit 1;}' /proc/uptime  ; then
                shutdown -r now "lsusb error. Rebooting to restore USB subsystem"
        fi
     fi
  fi
  
  exit 1
else
  echo "CGM Data $TIME_SINCE mins ago is fresh (< $OLD)"
  exit 0
fi

