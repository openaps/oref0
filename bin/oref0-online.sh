#!/bin/bash
echo; echo Starting oref0-online.
echo -n "At $(date) my local IP is: "
ifconfig | grep -A1 wlan0 | grep "inet " | awk '{print $2}' | awk -F : '{print $2}'
ifconfig | grep -A1 bnep0 | grep "inet " | awk '{print $2}' | awk -F : '{print $2}'
echo
echo -n "At $(date) my public IP is: "
if curl -m 15 icanhazip.com; then
    # if we are back on wifi (and have connectivity to icanhazip.com), shut down bluetooth
    if ( ifconfig | grep -A1 wlan0 | grep -q "inet addr" ) && ( ifconfig | grep -A1 bnep0 | grep -q "inet addr" ); then
        echo "Back online via wifi; disconnecting BT $MAC"
        ifdown bnep0
        # loop over as many MACs as are provided as arguments
        for MAC; do
            sudo bt-pan client $MAC -d
        done
        echo "and getting new wlan0 IP"
        ps aux | grep -v grep | grep -q "dhclient wlan0" && sudo killall dhclient
        sudo dhclient wlan0 -r
        sudo dhclient wlan0
    fi
else
    echo; echo "Error, cycling networking "
    # simply restart networking completely for stability purposes
    sudo /etc/init.d/networking stop
    sleep 5
    sudo /etc/init.d/networking start
    echo "and getting new wlan0 IP"
    ps aux | grep -v grep | grep -q "dhclient wlan0" && sudo killall dhclient
    sudo dhclient wlan0 -r
    sudo dhclient wlan0
    echo
    echo -n "At $(date) my public IP is: "
    # loop over as many MACs as are provided as arguments
    if ! curl -m 15 icanhazip.com; then
        echo
        for MAC; do
            echo -n "At $(date) my public IP is: "
            if ! curl -m 15 icanhazip.com; then
                echo; echo -n "Error, connecting BT to $MAC"
                oref0-bluetoothup
                sudo bt-pan client $MAC
                echo -n ", getting bnep0 IP"
                sudo dhclient bnep0
                # if we couldn't reach the Internet over wifi, but we have a bnep0 IP, release the wifi IP/route
                if ( ifconfig | grep -A1 wlan0 | grep -q "inet addr" ) && ( ifconfig | grep -A1 bnep0 | grep -q "inet addr" ); then
                    echo -n " and releasing wifi IP"
                    sudo dhclient wlan0 -r
                fi
                echo
            fi
        done
        echo
    fi
    echo -n "At $(date) my public IP is: "
    curl -m 15 icanhazip.com
fi
echo Finished oref0-online.
