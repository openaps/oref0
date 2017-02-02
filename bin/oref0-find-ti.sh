#!/bin/sh

#use this to bypass the automatic detection
#for example when you have slice of radio/EMF or TI-stick with Intel/Sparx Breakout board with Edison
#echo /dev/ttyAMA0
#exit 0

# Assume Explorerboard when /dev/spidev5.1 exists. This is not always true (e.g. Intel Edison with Intel/Sparx breakout board)
# if there is a better way to detect an Explorer board please fix
EXPLORER=/dev/spidev5.1
if [ -c $EXPLORER ]; then
	echo $EXPLORER
	exit 0
fi

# see if a TI-stick is available
A=`lsusb -d 1d50:8001 | wc -l`

if [ "$A" -eq "0" ]; then
     echo No TI stick, USB device idVendor=1d50, idProduct=8001 is found
     exit 1
fi

usbid=`dmesg | grep "idVendor=1d50, idProduct=8001" | tail -n 1 | sed -e 's/^.*usb \([0-9\.\-]*\):.*$/\1/g'`

if [ -z "$usbid" ]; then
     echo Could not find TI stick, USB device idVendor=1d50, idProduct=8001
     lsusb -d 1d50:8001
     exit 1
fi

device=/dev/`dmesg | grep "cdc_acm $usbid" | tail -n 1 | sed -e 's/^.*: \(tty[A-Z0-9]*\): USB.*$/\1/g'`

echo  $device
if [ -c $device ]; then
		A=`lsusb -d 1d50:8001 | wc -l`
        # see if TI-stick is still connected
        if [ "$A" -gt "0" ]; then
                exit 0
        else
                exit 1
        fi
else
        exit 0
fi

exit 1
