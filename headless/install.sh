#!/bin/bash

# Configure the system to be a headless server, copying in hostapd and other
# configs into the right place
#
# Copyright (c) 2015 OpenAPS Contributors
#
# Released under MIT license. See LICENSE.txt in the base directory of this
# repository
#

apt-get install -y hostapd dnsmasq
ls /etc/dnsmasq.conf.bak || mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
cp ./dnsmasq.conf /etc/dnsmasq.conf
ls /etc/hostapd/hostapd.conf.bak || mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bak
cp ./hostapd.conf /etc/hostapd/hostapd.conf
sed -i.bak -e "s|DAEMON_CONF=|DAEMON_CONF=/etc/hostapd/hostapd.conf|g" /etc/init.d/hostapd
cp interfaces.ap /etc/network/
cp /etc/network/interfaces /etc/network/interfaces.client
#ls $PWD/headless.sh && ( grep -q headless /etc/crontab || echo "* * * * * root $PWD/headless.sh" ) >> /etc/crontab
