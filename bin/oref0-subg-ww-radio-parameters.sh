#!/bin/bash

# This script must be started in the OpenAPS directory. 
# It requires subg_rfspy in installed. This can be installated with
#     cd ~/src
#     git clone https://github.com/ps2/subg_rfspy.git
#
SUBG_RFSPY_DIR=$HOME/src/subg_rfspy

# If you're on an ERF, set this to 0:
# export RFSPY_RTSCTS=0

# If you're using a TI USB set this to 1, otherwise set it to 0
# export TI_USB=0
export TI_USB=1

# Remember current directory. 
OPENAPS_DIR=`pwd`

################################################################################
set -e
set -x

# We'l try to find the TI device
# If it does not exist after the first minute (12*5 seconds), we'll try to get it back up:
# - we will use oref0-reset-usb (if you have a TI USB stick)
# - we will use the reset_spi_serial.py (if you have an Explorer board (with SERIAL_PORT that contains 'spi'))
# - otherwise we'll use the subg_rfspy reset.py
# If it does not exist after approx two minutes we'll issue a reset.py
# If still fails after 30*5+(2*15)=180 seconds it will exit with error status code
loop=0
until SERIAL_PORT=`oref0-get-pump-device`; do
   if  [[ "$loop" -eq "11" ]]; then
      if [[ "TI_USB" -eq "1" ]]; then
        sudo oref0-reset-usb
        # wait a bit more to let everything settle back
        sleep 15
      else 
        if [[ "$SERIAL_PORT" =~ "spi" ]]; then
          echo Resetting spi_serial
          reset_spi_serial.py
        else # no a TI usb and not a spidev (Explorer board)
          # Reset to defaults
          cd $SUBG_RFSPY_DIR/tools
          ./reset.py $SERIAL_PORT
          sleep 15
        fi
      fi
   fi
   if [[ "$loop" -eq "23" ]]; then
      # Reset to defaults
      cd $SUBG_RFSPY_DIR/tools
      ./reset.py $SERIAL_PORT
      sleep 15
   fi
   if [[ "$loop" -gt "30" ]]; then
      # exit the script with an error status
      exit 1
   fi
   # wait 5 seconds each iteration
   sleep 5
   # increment loop 
   ((loop=loop+1))
   # change back to openaps dir
   cd $OPENAPS_DIR
done

echo
echo Your TI device is located at $SERIAL_PORT

# change to subg_rfspy tools directory
cd $SUBG_RFSPY_DIR/tools

#Disabled killing openaps, because we want it to be able to use this with openaps mmtune
#echo -n "Killing running openaps processes... "
#killall -g openaps
#echo

# Disabled Reset to defaults, because it can hang the pump loop with TI USB stick
#./reset.py $SERIAL_PORT

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
