#!/bin/bash

if ( ifconfig wlan0 | grep -q "inet addr" ) && ( ifconfig bnep0 | grep -q "inet addr" ); then
   sudo killall bluetoothd
fi

if ! ( hciconfig -a | grep -q "PSCAN" ) ; then
   sudo killall bluetoothd
   sudo /usr/local/bin/bluetoothd --experimental &
fi

if ( hciconfig -a | grep -q "DOWN" ) ; then
   sudo hciconfig hci0 up
   sudo /usr/local/bin/bluetoothd --experimental &
fi

if !( hciconfig -a | grep -q $HOSTNAME ) ; then
   sudo hciconfig hci0 name $HOSTNAME
fi
