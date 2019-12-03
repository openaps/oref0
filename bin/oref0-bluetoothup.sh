#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Attempt to establish a Bluetooth tethering connection.
EOT

adapter=$(get_pref_string .bt_hci 2>/dev/null) || adapter=0

DAEMON_PATHS=(/usr/local/bin/bluetoothd /usr/libexec/bluetooth/bluetoothd /usr/sbin/bluetoothd)

# wait up to 3 seconds for hci name to be set
function wait_for_hci_name {
   max_wait_seconds=3
   elapsed_seconds=0
   while (( elapsed_seconds < max_wait_seconds )) && ! ( hciconfig -a hci${adapter} | grep -q "$HOSTNAME" )
   do
      sleep 1
      elapsed_seconds=$((elapsed_seconds + 1))
   done
   echo "$(date) Waited $elapsed_seconds second(s) for hci name to be set"
}

function stop_bluetooth {
   echo "$(date) Stopping bluetoothd..."
   if is_debian_jessie ; then
      sudo killall bluetoothd
   else
      sudo systemctl stop bluetooth
   fi
   echo "$(date) Stopped bluetoothd"
}

for EXEC_PATH in ${DAEMON_PATHS[@]}; do
  if [ -x $EXEC_PATH ]; then
    EXECUTABLE=$EXEC_PATH
    break;
  fi
done

if [ "$DEBUG" != "" ]; then
  EXECUTABLE="$EXECUTABLE -d -n"
fi

# start bluetoothd if bluetoothd is not running
# Added a bunch of if is_debian_jessie checks as stretch seems to behave better here.

if ! ( ps -fC bluetoothd >/dev/null ) ; then
   if is_debian_jessie ; then
      echo bluetoothd not running! Starting bluetoothd.
      sudo $EXECUTABLE 2>&1 | tee -a /var/log/openaps/bluetoothd.log &
   else
      echo bluetoothd not running! Starting bluetoothd via systemctl.
      sudo systemctl start bluetooth
   fi
fi

if is_edison && ! ( hciconfig -a hci${adapter} | grep -q "PSCAN" ) ; then
   if is_debian_jessie ; then
      echo Bluetooth PSCAN not enabled! Restarting bluetoothd...
      sudo killall bluetoothd 
      sudo $EXECUTABLE 2>&1 | tee -a /var/log/openaps/bluetoothd.log &
   else
      echo Bluetooth PSCAN not enabled! Restarting bluetoothd via systemctl...
      sudo systemctl restart bluetooth
   fi
fi

if ( hciconfig -a hci${adapter} | grep -q "DOWN" ) ; then
   # Not sure that this is needed on Stretch, add an is_debian_jessie check here if something different required.
   echo Bluetooth hci DOWN! Bringing it to UP.
   sudo hciconfig hci${adapter} up
 fi

if !( hciconfig -a hci${adapter} | grep -q $HOSTNAME ) ; then
   # Not sure that this is needed on Stretch, add an is_debian_jessie check here if something different required.
   echo Bluetooth hci name does not match hostname: $HOSTNAME. Setting bluetooth hci name.
   sudo hciconfig hci${adapter} name $HOSTNAME
   wait_for_hci_name
   if ! ( hciconfig -a hci${adapter} | grep -q "$HOSTNAME" ) ; then
      hciconfig -a hci${adapter}
      echo "$(date) Failed to set bluetooth hci name. Stop bluetoothd and allow next cycle to handle restart."
      stop_bluetooth
   fi
fi
