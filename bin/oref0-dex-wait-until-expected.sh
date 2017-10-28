#!/bin/bash

GLUCOSE=$1
OLD=${2-5}
MAX_WAIT=${3-1}
OLD_LSUSB=${4-12.0}
OA=$HOME/myopenaps
CGM_DIR=$OA/cgm
NS_GLUCOSE=$CGM_DIR/ns-glucose.json
REBOOT_ON_CGM_USB_ERROR=""
#OREF0_LOG_COMPONENT="cgm"
#OREF0_LOG_SUBCOMPOMENT="$0"

function reboot_on_cgm_usb_error {
  # return true if reboot_on_cgm_usb_error is set to true in preferences.json
  $(jq .reboot_on_cgm_usb_error $OA/preferences.json) = "true" > /dev/null
}

function oref0_log {
   # temporary log method, see discussion https://github.com/openaps/oref0/pull/759#issuecomment-340178012
   # $1: loglevel $2: message
   echo "$(date -Iseconds) $1 $2"
}

function ns_glucose_fresh {
    # check whether ns-glucose.json is less than 5m old
    touch -d "$(date -R -d @$(jq .[0].date/1000 $NS_GLUCOSE))" $NS_GLUCOSE
    find $CGM_DIR -mmin -$OLD_LSUSB | egrep -q "ns-glucose.json"
}

function enough_uptime {
    # check whether uptime is more than $1 minutes 
    UPTIME_IN_MINUTES=$(awk '{ print $0/60 }' /proc/uptime)
    (( $(bc <<< "$UPTIME_IN_MINUTES >= $1") ))
}

if [  -f $GLUCOSE ]; then
   TIME_SINCE=$(oref0-dex-time-since $GLUCOSE)

   if (( $(bc <<< "$TIME_SINCE >= $OLD") )); then
       oref0_log DEBUG "CGM Data $TIME_SINCE mins ago is old (>=$OLD), not waiting"
       # if there is no CGM for more than OLD_LSUSB minutes (default 8)
       # and there is no recent CGM from Nightscout (aged less than OLD_LSUSB minutes)
       # and the uptime of the system is more than OLD_LSUSB minutes (this prevents continuous reboots)
       # and the lsusb is failing (e.g. unable to initialize libusb: -99
       # reboot the system to restore the USB subsystem
       # this will make the CGM connected to the USB OTG work again
       if reboot_on_cgm_usb_error && (!ns_glucose_fresh) && enough_uptime $OLD_LSUSB; then
          if (( $(bc <<< "$TIME_SINCE >= $OLD_LSUSB") )); then
             if ! lsusb > /dev/null ; then
               oref0_log ERROR "Initiating reboot: CGM Data $TIME_SINCE mins ago is old (>=$OLD_LSUSB) and lsusb returns error: $(lsusb)"
               shutdown -r now "lsusb error. Rebooting to restore USB subsystem"
             fi
          fi
       fi
   else
      WAIT_MINS=$(bc <<< "$OLD - $TIME_SINCE")
      if (( $(bc <<< "$WAIT_MINS >= $MAX_WAIT") )); then
        oref0_log DEBUG "CGM Data $TIME_SINCE mins ago is fresh (< $OLD), $WAIT_MINS mins > max wait ($MAX_WAIT mins) waiting for next attempt"
        exit 1
      else
        oref0_log DEBUG "CGM Data $TIME_SINCE mins ago is fresh (< $OLD), waiting $WAIT_MINS mins for new data"
        sleep ${WAIT_MINS}m
        oref0_log DEBUG "finished waiting, let's get some CGM Data"
      fi
    fi
else
   oref0_log DEBUG "CGM not read from USB (yet). $GLUCOSE does not exist. "
   if [ -f $NS_GLUCOSE ]; then
       if ns_glucose_fresh; then
          oref0_log DEBUG "$NS_GLUCOSE has been updated less than $OLD_LSUSB minutes ago. Skipping reading from USB and using CGM data from Nightscout"
          exit 1
       else
          oref0_log DEBUG "$NS_GLUCOSE has not been updated for at least $OLD_LSUSB minutes."
          oref0_log DEBUG "Checking USB subsystem: $(lsusb)"
          if enough_uptime $OLD_LSUSB && ! lsusb > /dev/null ; then
             oref0_log ERROR "Initiating reboot: CGM Data not available on rig and Nightscout. lsusb returns error: $(lsusb)"
             shutdown -r now "lsusb error. Rebooting to restore USB subsystem"
          fi
        fi
   fi
fi


