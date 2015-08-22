#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

die() { echo "$@" ; exit 1; }

ntp-wait -n 1 -v && die "NTP already synchronized."

cd ~/openaps-dev
( cat clock.json; echo ) | sed 's/"//g' | sed "s/$/`date +%z`/" | while read line; do date -u -d $line +"%F %R:%S"; done > fake-hwclock.data
grep : fake-hwclock.data && sudo cp fake-hwclock.data /etc/fake-hwclock.data
sudo fake-hwclock load
grep -q display_time glucose.json && grep display_time glucose.json | head -1 | awk '{print $2}' | sed "s/,//" | sed 's/"//g' | sed "s/$/`date +%z`/" | while read line; do date -u -d $line +"%F %R:%S"; done > fake-hwclock.data
grep -q dateString glucose.json && grep dateString glucose.json | head -1 | awk '{print $2}' | sed "s/,//" | sed 's/"//g' |while read line; do date -u -d $line +"%F %R:%S"; done > fake-hwclock.data
grep : fake-hwclock.data && sudo cp fake-hwclock.data /etc/fake-hwclock.data
sudo fake-hwclock load
