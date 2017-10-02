#!/bin/bash
echo; echo Starting oref0-online.
# if we are connected to wifi but don't have an IP, try to get one
if iwgetid -r wlan0 | egrep -q "[A-Za-z0-9_]+"; then
    if ! ip route | grep default | grep -q wlan0; then
        echo Attempting to renew wlan0 IP
        sudo dhclient wlan0
    fi
fi
echo -n "At $(date) my local IP is: "
ip -4 -o addr show dev wlan0 | awk '{split($4,a,"/");print a[1]}'
ip -4 -o addr show dev bnep0 | awk '{split($4,a,"/");print a[1]}'
echo
echo -n "At $(date), my wifi network name is "
iwgetid -r wlan0 | tr -d '\n'
echo -n ", and my public IP is: "
if curl --compressed -4 -s -m 15 checkip.amazonaws.com | awk -F , '{print $NF}' | egrep "^[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]$"; then
    # if we are back on wifi (and have connectivity to checkip.amazonaws.com), shut down bluetooth
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
    echo
    echo -n "At $(date), my wifi network name is "
    iwgetid -r wlan0 | tr -d '\n'
    echo -n ", and my public IP is: "
    # loop over as many MACs as are provided as arguments
    if ! curl --compressed -4 -s -m 15 checkip.amazonaws.com | awk -F , '{print $NF}' | egrep "^[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]$"; then
        echo
        for MAC; do
            echo -n "At $(date) my public IP is: "
            if ! curl --compressed -4 -s -m 15 checkip.amazonaws.com | awk -F , '{print $NF}' | egrep "^[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]$"; then
                echo; echo -n "Error, connecting BT to $MAC"
                oref0-bluetoothup
                sudo bt-pan client $MAC -d
                sudo bt-pan client $MAC
                echo -n ", getting bnep0 IP"
                sudo dhclient bnep0
                # if we couldn't reach the Internet over wifi, but we have a bnep0 IP, release the wifi IP/route
                if ( ifconfig | grep -A1 wlan0 | grep -q "inet addr" ) && ( ifconfig | grep -A1 bnep0 | grep -q "inet addr" ); then
                    echo -n " and releasing wifi IP"
                    sudo dhclient wlan0 -r
                    echo
                    echo Sleeping for 2 minutes before trying wifi again
                    sleep 120
                fi
                echo
            fi
        done
        echo
    fi
    echo -n "At $(date), my wifi network name is "
    iwgetid -r wlan0 | tr -d '\n'
    echo -n ", and my public IP is: "
    # if we still can't get online, try cycling networking as a last resort
    if ! curl --compressed -4 -s -m 15 checkip.amazonaws.com | awk -F , '{print $NF}' | egrep "^[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]$"; then
        echo; echo "Error, cycling networking "
        sudo /etc/init.d/networking stop
        sleep 5
        sudo /etc/init.d/networking start
        echo "and getting new wlan0 IP"
        ps aux | grep -v grep | grep -q "dhclient wlan0" && sudo killall dhclient
        sudo dhclient wlan0 -r
        sudo dhclient wlan0
    fi
fi
# restart avahi every minute to keep mDNS working properly
#/etc/init.d/avahi-daemon restart
echo Finished oref0-online.
