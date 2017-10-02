#!/bin/bash

main() {
    echo; echo Starting oref0-online.
    # if we are connected to wifi but don't have an IP, try to get one
    if iwgetid -r wlan0 | egrep -q "[A-Za-z0-9_]+"; then
        if ! ip route | grep default | grep -q wlan0; then
            echo Attempting to renew wlan0 IP
            sudo dhclient wlan0
        fi
    fi
    echo -n "At $(date) my local IP is: "
    print_local_ip wlan0
    print_local_ip bnep0
    echo
    print_wifi_name
    if check_ip; then
        # if we are back on wifi (and have connectivity to checkip.amazonaws.com), shut down bluetooth
        if has_addr wlan0 && has_addr bnep0; then
            bt_disconnect
        fi
    else
        echo
        print_wifi_name
        if ! check_ip; then
            bt_connect
        fi
        print_wifi_name
        if ! check_ip; then
            # if we still can't get online, try cycling networking as a last resort
            restart_networking
        fi
    fi
    echo Finished oref0-online.
}

function print_wifi_name {
    echo -n "At $(date), my wifi network name is "
    iwgetid -r wlan0 | tr -d '\n'
    echo -n ", and my public IP is: "
}

function print_local_ip {
    ip -4 -o addr show dev $1 | awk '{split($4,a,"/");print a[1]}'
}

function check_ip {
    curl --compressed -4 -s -m 15 checkip.amazonaws.com | awk -F , '{print $NF}' | egrep "^[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]$"
}

function has_addr {
    ifconfig | grep -A1 $1 | grep -q "inet addr"
}

function bt_connect {
    # loop over as many MACs as are provided as arguments
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
            # if we couldn't reach the Internet over wifi, but (now) have a bnep0 IP, release the wifi IP/route
            if has_addr wlan0 && has_addr bnep0; then
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
}

function bt_disconnect {
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
}

function restart_networking {
    echo; echo "Error, cycling networking "
    sudo /etc/init.d/networking stop
    sleep 5
    sudo /etc/init.d/networking start
    echo "and getting new wlan0 IP"
    ps aux | grep -v grep | grep -q "dhclient wlan0" && sudo killall dhclient
    sudo dhclient wlan0 -r
    sudo dhclient wlan0
}

main "$@"
