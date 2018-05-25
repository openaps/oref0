#!/bin/bash

main() {
    MACs=$@
    HostAPDIP='10.29.29.1'
    echo; echo Starting oref0-online at $(date).
    #Need to add "presistent_btpan": true to the end of the preferences.json file to enable PersistentBT Pan
    if  cat preferences.json | jq -e .persistent_btpan > /dev/null; then
        PersistentBTPAN="true"
        echo "At $(date) PersistentBT Pan is enabled"
    else
        PersistentBTPAN="false"
    fi
    # if we are connected to wifi but don't have an IP, try to get one
    if iwgetid -r wlan0 | egrep -q "[A-Za-z0-9_]+"; then
        if ! ip route | grep default | grep -q wlan0; then
            if find /tmp/ -mmin -60 | grep bad_wifi && grep -q "$(iwgetid -r wlan0)" /tmp/bad_wifi; then
                echo Not renewing wlan0 IP due to recent connectivity failure:
                ls -la /tmp/bad_wifi
            else
                echo Attempting to renew wlan0 IP
		ip route del 0/0
                sudo dhclient wlan0 -r -q
                sudo dhclient wlan0
            fi
        fi
    fi
        echo "At $(date) my gateway is: $(ip route | awk '/default/ {print $3}') via interface $(ip route | awk '/default/ {print $5}')"
	if ifconfig | egrep -q "wlan0" >/dev/null; then
        #if [[ $(ip -4 -o addr show dev wlan0 | awk '{split($4,a,"/");print a[1]}') = $(print_local_ip wlan0) ]]; then
                print_wifi_name
        echo -n "At $(date) my local wifi IP is: "
        print_local_ip wlan0
        fi
        if ifconfig | egrep -q "bnep0" >/dev/null; then
                #if [[ $(ip -4 -o addr show dev bnep0 | awk '{split($4,a,"/");print a[1]}') = $(print_local_ip bnep0) ]]; then
                        print_bluetooth_name
                #fi
            if ! has_ip bnep0; then
                sudo dhclient bnep0
            fi
            echo -n "At $(date) my local Bluetooth IP is: "
            print_local_ip bnep0
        else
            if [ "$PersistentBTPAN" = "true" ] ; then
                echo "At $(date) my Bluetooth PAN is not connected, trying to connect now"
                bt_connect $MACs
            else
                echo "At $(date) my Bluetooth PAN is not connected"
            fi
        fi
        echo -n "At $(date) my public IP is: "
    if check_ip; then
        stop_hotspot
        if has_ip wlan0 && has_ip bnep0; then
            # if online via BT w/o a DHCP IP, cycle wifi
            if print_local_ip wlan0 | grep $HostAPDIP || ! has_ip wlan0; then
                ifdown wlan0; ifup wlan0
            fi
        fi
        # if online via wifi, disconnect BT if no persistent PAN
        if has_ip wlan0 && ifconfig | egrep -q "bnep0" >/dev/null; then
            if [ "$PersistentBTPAN" != "true" ] ; then
                bt_disconnect $MACs
                #wifi_dhcp_renew
            fi
        fi
    else
        echo
        print_wifi_name
        if ! has_ip wlan0; then
            wifi_dhcp_renew
        fi
        if has_ip bnep0; then
	    #check if default route is using BT PAN, if not remove all gateways and release/renew bt dhcp lease
            if ! ip route get 8.8.8.8 | egrep -q "bnep0" >/dev/null; then
                ip route del 0/0
                sudo dhclient bnep0 -r -q
                sudo dhclient bnep0
            fi
        else
            bt_connect $MACs
        fi

        #print_wifi_name
        if check_ip >/dev/null; then
            # if we're online after activating bluetooth, shut down any local-access hotspot we're running
            stop_hotspot
                        if ! print_local_ip wlan0 | egrep -q "[A-Za-z0-9_]+" >/dev/null; then
                                wifi_dhcp_renew
                        fi
        else
            # if we can't connect via BT, might as well try previously bad wifi networks again
            rm /tmp/bad_wifi
            # if we can't get online via wifi or bluetooth, start our own local-access hotspot
            start_hotspot $@
            # don't disconnect bluetooth when starting local-only hotspot
        fi
    fi
    echo Finished oref0-online at $(date).
}

function print_bluetooth_name {
    echo -n "At $(date) my Bluetooth is connected to "
    grep Name /var/lib/bluetooth/*/*/info | awk -F = '{print $2}'
    #echo ${MACs}
}

function print_wifi_name {
    SSID=$(iwgetid -r wlan0 | tr -d '\n')
    if [[ ! -z $SSID ]]; then
        echo "At $(date) my wifi network name is $SSID"
    else
        echo "At $(date) my wifi is not connected"
    fi
}

function print_local_ip {
    LOCAL_IP=$(ip -4 -o addr show dev $1 | awk '{split($4,a,"/");print a[1]}')
    if [[ -z $LOCAL_IP ]]; then
        echo unassigned
    else
        echo $LOCAL_IP
    fi
}

function check_ip {
    PUBLIC_IP=$(curl --compressed -4 -s -m 15 checkip.amazonaws.com | awk -F , '{print $NF}' | egrep "^[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]\.[12]*[0-9]*[0-9]$")
    if [[ -z $PUBLIC_IP ]]; then
        echo not found
        return 1
    else
        echo $PUBLIC_IP
    fi
}

function has_ip {
    ifconfig | grep -A1 $1 | grep -q "inet addr"
}

function bt_connect {
    # loop over as many MACs as are provided as arguments
    for MAC; do
        #echo -n "At $(date) my public IP is: "
        if [ "$PersistentBTPAN" == "true" ]; then
            if has_ip bnep0; then
                break
            fi
            echo; echo "No BT PAN detected, attempting to connect BT to $MAC"
        else
            if check_ip > /dev/null; then
                break
            fi
            echo; echo "No Internet access detected, attempting to connect BT to $MAC"
        fi
        oref0-bluetoothup
        sudo bt-pan client $MAC -d
        sudo bt-pan client $MAC && sudo dhclient bnep0
        if ifconfig | egrep -q "bnep0" >/dev/null; then
            if ! has_ip bnep0; then
                sudo dhclient bnep0
            fi
            echo -n "Connected to Bluetooth with IP: "
            print_local_ip bnep0
        fi
        # if we couldn't reach the Internet over wifi, but (now) have a bnep0 IP, release the wifi IP/route
        if has_ip wlan0 && has_ip bnep0 && ! grep -q $HostAPDIP /etc/network/interfaces; then
            #check if Persistent Pan
            if [ "$PersistentBTPAN" == "true" ] ; then
                #check if BT is routing traffic
                if ip route get 8.8.8.8 | egrep -q "bnep0" >/dev/null; then
                            # release the wifi IP/route but *don't* renew it, in case it's not working
                            sudo dhclient wlan0 -r
                            iwgetid -r wlan0 >> /tmp/bad_wifi
                fi
            else
                sudo dhclient wlan0 -r
                        iwgetid -r wlan0 >> /tmp/bad_wifi   
            fi
        fi
        #echo
    done
}

function bt_disconnect {
    #check if Persistent Pan
    if [ "$PersistentBTPAN" != "true" ] ; then
        echo "Disconnecting BT $MAC"
        ifdown bnep0
        # loop over as many MACs as are provided as arguments
        for MAC; do
            sudo bt-pan client $MAC -d
        done
    fi
}

function wifi_dhcp_renew {
    if find /tmp/ -mmin -60 | grep bad_wifi && grep -q "$(iwgetid -r wlan0)" /tmp/bad_wifi; then
        echo Not renewing wlan0 IP due to recent connectivity failure:
        ls -la /tmp/bad_wifi
    else
        echo; echo "Getting new wlan0 IP"
        ps aux | grep -v grep | grep -q "dhclient wlan0" && sudo killall dhclient
        sudo dhclient wlan0 -r -q
        sudo dhclient wlan0
    fi
}

function stop_hotspot {
    if grep -q $HostAPDIP /etc/network/interfaces || iwconfig wlan0 | grep Mode:Master; then
        echo "Shutting down local-only hotspot"
        echo "Attempting to stop hostapd"
        /etc/init.d/hostapd stop
        echo "Attempting to stop dnsmasq"
        /etc/init.d/dnsmasq stop
        echo "Activating client config"
        ifdown wlan0
        cp /etc/network/interfaces.client /etc/network/interfaces
        ifup wlan0
        echo "Renewing IP Address for wlan0"
        dhclient_restart
    else
        echo -n "At $(date) my local hotspot is not running"
        if ! cat preferences.json | jq -e .offline_hotspot >/dev/null; then
            echo " (and not enabled in preferences.json)"
        else
            echo
        fi
    fi
}

function stop_cycle {
    stop_hotspot
    echo "Cycling wlan0"
    ifdown wlan0; ifup wlan0
}


function start_hotspot {
    echo
    if ls /tmp/disable_hotspot; then
        stop_cycle
    elif ! ls preferences.json 2>/dev/null >/dev/null \
        || ! cat preferences.json | jq -e .offline_hotspot >/dev/null; then
        echo "Offline hotspot not enabled in preferences.json"
        stop_cycle
    elif [[ -z $1 ]]; then
        echo "No BT MAC provided: not activating local-only hotspot"
        echo "Cycling wlan0"
        ifdown wlan0; ifup wlan0
    elif grep -q $HostAPDIP /etc/network/interfaces \
        && ifconfig wlan0 | grep -q $HostAPDIP; then
        echo "Local hotspot is running."
        service hostapd status > /dev/null || service hostapd restart
        service dnsmasq status > /dev/null || service dnsmasq restart
    elif ! ls /etc/network/interfaces.ap 2>/dev/null >/dev/null; then
        echo "Local-only hotspot not configured"
        stop_cycle
    else
        echo "Unable to connect via wifi or Bluetooth; activating local-only hotspot"
        echo "Killing wpa_supplicant"
        #killall wpa_supplicant
        wpa_cli terminate
        echo "Shutting down wlan0"
        ifdown wlan0
        echo "Activating AP config"
        cp /etc/network/interfaces.ap /etc/network/interfaces
        ifup wlan0
        echo "Attempting to start hostapd"
        /etc/init.d/hostapd start
        echo "Attempting to start dnsmasq"
        service udhcpd stop
        /etc/init.d/dnsmasq start
        systemctl daemon-reload
        #echo "Stopping networking"
        #/etc/init.d/networking stop
        #echo "Starting networking"
        #/etc/init.d/networking start
        sleep 5
        echo "Setting IP Address for wlan0"
        /sbin/ifconfig wlan0 $HostAPDIP netmask 255.255.255.0 up
    fi
}

function dhclient_restart {
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
    dhclient_restart
}

main "$@"
