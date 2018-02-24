#!/bin/bash

# start bluetoothd if bluetoothd is not running
if ! ( ps -fC bluetoothd ) ; then
   sudo /usr/local/bin/bluetoothd &
fi

#Raspberry Pi doesn't keep PSCAN up the way Edison does. Check for ARM CPU (vs x86 on Edison) before executing this bloc
sys_arch=$(uname -m)
if [ ! -z "${sys_arch##*arm*}" ]
then
   if ! ( hciconfig -a | grep -q "PSCAN" ) ; then
      echo "On Edison and no PSCAN - restarting bluetoothd"
      sudo killall bluetoothd
      sudo /usr/local/bin/bluetoothd &
   fi
fi

if ( hciconfig -a | grep -q "DOWN" ) ; then
   sudo hciconfig hci0 up
   sudo /usr/local/bin/bluetoothd &
fi

if !( hciconfig -a | grep -q $HOSTNAME ) ; then
   sudo hciconfig hci0 name $HOSTNAME
fi
