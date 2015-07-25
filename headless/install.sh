#!/bin/bash

apt-get install -y hostapd dnsmasq
mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
cp ./dnsmasq.conf /etc/dnsmasq.conf
mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bak
cp ./hostapd.conf /etc/hostapd/hostapd.conf
sed -i.bak -e "s|DAEMON_CONF=|DAEMON_CONF=/etc/hostapd/hostapd.conf|g" /etc/init.d/hostapd
cp interfaces.* /etc/network/
ls $PWD/headless.sh && ( grep -q headless /etc/crontab || echo "* * * * * root $PWD/headless.sh" ) >> /etc/crontab
