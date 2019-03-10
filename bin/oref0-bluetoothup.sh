#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Attempt to establish a Bluetooth tethering connection.
EOT

adapter=$(get_pref_string bt_hci) || adapter=0

# start bluetoothd if bluetoothd is not running
if ! ( ps -fC bluetoothd >/dev/null ) ; then
   sudo /usr/local/bin/bluetoothd &
fi

if is_edison && ! ( hciconfig -a | grep -q "PSCAN" ) ; then
   sudo killall bluetoothd
   sudo /usr/local/bin/bluetoothd &
fi

if ( hciconfig -a | grep -q "DOWN" ) ; then
   sudo hciconfig hci${adapter} up
   sudo /usr/local/bin/bluetoothd &
fi

if !( hciconfig -a | grep -q $HOSTNAME ) ; then
   sudo hciconfig hci${adapter} name $HOSTNAME
fi
