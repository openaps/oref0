#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Attempt to establish a Bluetooth tethering connection.
EOT

adapter=$(get_pref_string .bt_hci 2>/dev/null) || adapter=0

DAEMON_PATHS=(/usr/local/bin/bluetoothd /usr/libexec/bluetooth/bluetoothd /usr/sbin/bluetoothd)

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
fi
