#!/bin/bash

apt-get install -y hostapd dnsmasq
mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
cp ./dnsmasq.conf /etc/dnsmasq.conf
mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bak
cp ./hostapd.conf /etc/hostapd/hostapd.conf
cp interfaces.* /etc/network/
ls $PWD/headless.sh && ( grep headless /etc/crontab || echo "* * * * * root $PWD/headless.sh" ) >> /etc/crontab
