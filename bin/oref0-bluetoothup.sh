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
if ! ( ps -fC bluetoothd >/dev/null ) ; then
   echo bluetoothd not running! Starting bluetoothd...
   sudo $EXECUTABLE 2>&1 | tee -a /var/log/openaps/bluetoothd.log &
fi

if is_edison && ! ( hciconfig -a hci${adapter} | grep -q "PSCAN" ) ; then
   echo Bluetooth PSCAN not enabled! Restarting bluetoothd...
   sudo killall bluetoothd
   sudo $EXECUTABLE 2>&1 | tee -a /var/log/openaps/bluetoothd.log &
fi

if ( hciconfig -a hci${adapter} | grep -q "DOWN" ) ; then
   echo Bluetooth hci DOWN! Bringing it to UP.
   sudo hciconfig hci${adapter} up
   sudo $EXECUTABLE 2>&1 | tee -a /var/log/openaps/bluetoothd.log &
fi

if !( hciconfig -a hci${adapter} | grep -q $HOSTNAME ) ; then
   echo Bluetooth hci name does not match hostname: $HOSTNAME. Setting bluetooth hci name.
   sudo hciconfig hci${adapter} name $HOSTNAME
fi
