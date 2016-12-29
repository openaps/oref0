#!/bin/bash

# Set this to the serial port that your device is on: eg /dev/ttyACM0 or /dev/ttyMFD1
# use oref0-find-ti-usb-device.sh to autodetect the ACM device of the TI USB stick
SERIAL_PORT=`/usr/local/bin/oref0-find-ti`
#SERIAL_PORT="/dev/ttyS0"
echo Your TI-stick is located at $SERIAL_PORT

# Set this to the directory where you've run this. By default:
#     cd ~
#     git clone https://github.com/ps2/subg_rfspy.git
#
SUBG_RFSPY_DIR=$HOME/src/subg_rfspy

# If you're on an ERF, set this to 0:
# export RFSPY_RTSCTS=0

################################################################################
set -e
set -x

cd $SUBG_RFSPY_DIR/tools

#disabled killing openaps, because we want it to be able to use this with openaps mmtune
#echo -n "Killing running openaps processes... "
#killall -g openaps
#echo

# Reset to defaults
./reset.py $SERIAL_PORT

sleep 2

./change_setting.py $SERIAL_PORT 0x06 0x00          # CHANNR

sleep 0.5

./change_setting.py $SERIAL_PORT 0x0C 0x59          # MDMCFG4
sleep 0.5
./change_setting.py $SERIAL_PORT 0x0D 0x66          # MDMCFG3
sleep 0.5
./change_setting.py $SERIAL_PORT 0x0E 0x33          # MDMCFG2
sleep 0.5
./change_setting.py $SERIAL_PORT 0x0F 0x62          # MDMCFG1
sleep 0.5
./change_setting.py $SERIAL_PORT 0x10 0x1A          # MDMCFG0
sleep 0.5

./change_setting.py $SERIAL_PORT 0x11 0x13          # DEVIATN
sleep 0.5

./change_setting.py $SERIAL_PORT 0x09 0x24          # FREQ2
sleep 0.5
./change_setting.py $SERIAL_PORT 0x0A 0x2E          # FREQ1
sleep 0.5
./change_setting.py $SERIAL_PORT 0x0B 0x38          # FREQ0
sleep 0.5

exit 0
