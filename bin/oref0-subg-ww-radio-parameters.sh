#!/bin/bash

# set SERIAL_PORT from environment variable, or first argument, or default to /dev/mmeowlink
SERIAL_PORT=${SERIAL_PORT-${1-/dev/mmeowlink}}

# It requires subg_rfspy in installed. This can be installated with
#     cd ~/src
#     git clone https://github.com/ps2/subg_rfspy.git
# Set SUBG_RFSPY_DIR to your subg_rfspy checkout
SUBG_RFSPY_DIR=$HOME/src/subg_rfspy

# If you're on an ERF or TI USB, set this to 0:
#export RFSPY_RTSCTS=0

################################################################################
set -e
# use set -x to debug oref0 ww pump communication errors
# set -x

echo
echo The CC111x is located at $SERIAL_PORT

# change to subg_rfspy tools directory
cd $SUBG_RFSPY_DIR/tools

#Disabled killing openaps, because we want it to be able to use this with openaps mmtune
#echo -n "Killing running openaps processes... "
#killall -g openaps
#echo

# Disabled by default, because it can hang the pump loop with TI USB stick
# The reset.py script will be called if this script is run with --resetpy as second parameter
# This is the default behaviour implemented in oref0_init_pump_comms.py
case "$2" in
  --resetpy)
    ./reset.py $SERIAL_PORT
    sleep 2
    exit 0
    ;;
esac

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
