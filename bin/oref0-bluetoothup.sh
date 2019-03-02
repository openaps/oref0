#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Attempt to establish a Bluetooth tethering connection.
EOT

DAEMON_PATHS=(/usr/local/bin/bluetoothd /usr/libexec/bluetooth/bluetoothd /usr/sbin/bluetoothd)

for EXEC_PATH in ${DAEMON_PATHS[@]}; do
  if [ -x $EXEC_PATH ]; then
    EXECUTABLE=$EXEC_PATH
    break;
  fi
done

# start bluetoothd if bluetoothd is not running
if ! ( ps -fC bluetoothd >/dev/null ) ; then
   echo bluetoothd not running! Starting bluetoothd...
   sudo $EXECUTABLE &
fi

if is_edison && ! ( hciconfig -a | grep -q "PSCAN" ) ; then
   echo Bluetooth PSCAN not enabled! Restarting bluetoothd...
   sudo killall bluetoothd
   sudo $EXECUTABLE &
fi

if ( hciconfig -a | grep -q "DOWN" ) ; then
   echo Bluetooth hci DOWN! Bringing it to UP.
   sudo hciconfig hci0 up
   sudo $EXECUTABLE &
fi

if !( hciconfig -a | grep -q $HOSTNAME ) ; then
   echo Bluetooth hci name does not match hostname: $HOSTNAME. Setting bluetooth hci name.
   sudo hciconfig hci0 name $HOSTNAME
fi
