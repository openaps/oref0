#!/bin/bash
MAC=$1
echo -n "At $(date) my IP is: "
if ! curl -m 15 icanhazip.com; then
    echo -n "Error, cycling networking "
   # sudo ifdown wlan0
  #  sudo ifup wlan0
  #  echo -n "and getting new wlan0 IP"
   # ps aux | grep -v grep | grep -q "dhclient wlan0" && sudo killall dhclient
   # sudo dhclient wlan0 -r
  #  sudo dhclient wlan0
  #modify prior script to simply restart networking completely for stability purposes
  /etc/init.d/networking stop
  sleep 5
  /etc/init.d/networking start
    echo
    echo -n "At $(date) my IP is: "
    if ! curl -m 15 icanhazip.com; then
        echo -n "Error, connecting BT to $MAC "
        sudo killall bluetoothd; sudo /usr/local/bin/bluetoothd --experimental &
        sudo bt-pan client $MAC
        echo -n "and getting bnep0 IP"
        sudo dhclient bnep0
        echo
        echo -n "At $(date) my IP is: "
        curl -m 15 icanhazip.com
        echo
    fi
fi
