#!/bin/bash

# Interface checker
# Checks to see whether interface has an IP address, if it doesn't assume it's
# down and start hostapd
#
# Original Author : SirLagz
# Extensive modifications by scottleibrand
#
# Copyright (c) 2015 OpenAPS Contributors
#
# Released under MIT license. See the accompanying LICENSE.txt file for
# full terms and conditions
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

Interface='wlan0'
HostAPDIP='10.29.29.1'
echo "-----------------------------------"
echo "Checking for DHCP leases"
clients=$(cat /var/lib/misc/dnsmasq.leases | wc -l)
echo "$clients DHCP clients found"
if [[ $clients -eq 0 ]]; then
    hostapd=$(pidof hostapd)
    if [[ ! -z $hostapd ]]; then
        echo "Activating client config"
        cp /etc/network/interfaces.client /etc/network/interfaces
        echo "Attempting to stop hostapd"
        /etc/init.d/hostapd stop
        echo "Attempting to stop dnsmasq"
        /etc/init.d/dnsmasq stop
        echo "Stopping networking"
        /etc/init.d/networking stop
        echo "Starting networking"
        /etc/init.d/networking start
        wpasup=$(pidof wpa_supplicant)
        if [[ -z $wpasup ]]; then
            echo "Attempting to start wpa_supplicant"
            sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
        fi
        echo "Renewing IP Address for $Interface"
        /sbin/dhclient wlan0
    else
        echo "Checking connectivity of $Interface"
        NetworkUp=$(/sbin/ifconfig $Interface)
        IP=$(echo "$NetworkUp" | grep inet | wc -l)
        if [[ $IP -eq 0 || $NetworkUp =~ $HostAPDIP ]]; then
        #if [[ $IP -eq 0 ]]; then
            #echo "Connection is down"

            hostapd=$(pidof hostapd)
            if [[ -z $hostapd ]]; then
                # If there are any more actions required when the interface goes down, add them here
                echo "Killing wpa_supplicant"
                #killall wpa_supplicant
                wpa_cli terminate
                echo "Activating AP config"
                cp /etc/network/interfaces.ap /etc/network/interfaces
                echo "Attempting to start hostapd"
                /etc/init.d/hostapd start
                echo "Attempting to start dnsmasq"
                /etc/init.d/dnsmasq start
                echo "Stopping networking"
                /etc/init.d/networking stop
                echo "Starting networking"
                /etc/init.d/networking start
                sleep 5
                echo "Setting IP Address for wlan0"
                /sbin/ifconfig wlan0 $HostAPDIP netmask 255.255.255.0 up
            fi
        #elif [[ $IP -eq 1 && $NetworkUp =~ $HostAPDIP ]]; then
            #echo "IP is $HostAPDIP - hostapd is running"
        else
            echo "Connection is up"
        fi
    fi
fi
echo "-----------------------------------"
