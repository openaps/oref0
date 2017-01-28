#!/bin/bash

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

# We'll use the device that is set in the pump.ini config file in the openaps directory
# This script must be started from the openaps dir
echo -n "Searching for pump device: "

# We'l try to find the TI device
# If it does not exist we will use oref0-reset usb after a minute (12*5 seconds) to get it back up
# If it fails the second time exit with error status code
loop=0
until SERIAL_PORT=`oref0-get-pump-device`; do
   if  [ "$loop" -gt "11" || "$loop" -gt "23" ]; then
      sudo oref0-reset-usb
      # wait a bit more to let everything settle back
      sleep 10
   fi
   if ["$loop" -gt "30" ]; then
      # exit the script with an error status
      exit 1
   fi
   echo -n "."
   sleep 5
   ((loop=loop+1))
done

echo
echo Your TI device is located at $SERIAL_PORT

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
