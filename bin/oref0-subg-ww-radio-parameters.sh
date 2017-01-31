#!/bin/bash

# It requires subg_rfspy in installed. This can be installated with
#     cd ~/src
#     git clone https://github.com/ps2/subg_rfspy.git
#
SUBG_RFSPY_DIR=$HOME/src/subg_rfspy

# If you're on an ERF or TI USB, set this to 0:
#export RFSPY_RTSCTS=0

################################################################################
set -e
set -x

echo
echo Your TI device is located at $SERIAL_PORT

if [ -c $SERIAL_PORT]; 
  echo "ERROR: TI device is not found or not a serial device. Make sure you set SERIAL_PORT environment variable to the right file"
  exit 1 
fi

# change to subg_rfspy tools directory
cd $SUBG_RFSPY_DIR/tools

#Disabled killing openaps, because we want it to be able to use this with openaps mmtune
#echo -n "Killing running openaps processes... "
#killall -g openaps
#echo

# Disabled Reset to defaults, because it can hang the pump loop with TI USB stick
# ./reset.py $SERIAL_PORT

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
