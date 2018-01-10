#!/bin/bash

# start bluetoothd if bluetoothd is not running
if ! ( ps -fC bluetoothd ) ; then
   sudo /usr/local/bin/bluetoothd &
fi

if ! ( hciconfig -a | grep -q "PSCAN" ) ; then
   sudo killall bluetoothd
   sudo /usr/local/bin/bluetoothd &
fi

if ( hciconfig -a | grep -q "DOWN" ) ; then
   sudo hciconfig hci0 up
   sudo /usr/local/bin/bluetoothd &
fi

if !( hciconfig -a | grep -q $HOSTNAME ) ; then
   sudo hciconfig hci0 name $HOSTNAME
fi
