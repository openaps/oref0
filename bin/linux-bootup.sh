#!/bin/bash

#This Bash script run in /etc/rc.local
#Can be used for anything that is needed to run during startup

#Interrupting Kernel Messages in Console/Screen
sudo dmesg -n 1

# Check if the /etc/network/interface was left with Wifi hotspot mode, moves it back to wifi client mode
ifgrep -Fxq "wpa-conf /etc/wpa_supplicant/wpa_supplicant.conf" "/etc/network/interfaces"
  sudo ifdown wlan0
  sudo cp /etc/network/interfaces.client /etc/network/interfaces
  sudo ifup wlan0
fi  
