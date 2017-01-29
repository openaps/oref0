#!/bin/bash
MAC=$1
MAC2=$2
echo -n "At $(date) my local IP is: "
ifconfig wlan0 | grep "inet " | awk '{print $2}' | awk -F : '{print $2}'
ifconfig bnep0 | grep "inet " | awk '{print $2}' | awk -F : '{print $2}'
echo -n "At $(date) my public IP is: "
if ! curl -m 15 icanhazip.com; then
    echo -n "Error, cycling networking "
    # simply restart networking completely for stability purposes
    sudo /etc/init.d/networking stop
    sleep 5
    sudo /etc/init.d/networking start
    echo -n "and getting new wlan0 IP"
    ps aux | grep -v grep | grep -q "dhclient wlan0" && sudo killall dhclient
    sudo dhclient wlan0 -r
    sudo dhclient wlan0
    echo
    echo -n "At $(date) my public IP is: "
    if ! curl -m 15 icanhazip.com; then
        echo -n "Error, connecting BT to $MAC "
        oref0-bluetoothup
        sudo bt-pan client $MAC
        echo -n "and getting bnep0 IP"
        sudo dhclient bnep0
        echo
        echo -n "At $(date) my public IP is: "
        if ! curl -m 15 icanhazip.com; then
            if [[ ! -z "${MAC2}" ]]; then
                echo -n "Error, connecting BT to $MAC2 "
                oref0-bluetoothup
                sudo bt-pan client $MAC2
                echo -n "and getting bnep0 IP"
                sudo dhclient bnep0
                echo
                echo -n "At $(date) my public IP is: "
            fi
        fi
        echo
    fi
fi
