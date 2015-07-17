#!/bin/bash
cd ~/openaps-dev
#eval `ssh-agent -s`
#ssh-add /home/sleibrand/.ssh/id_rsa.sleibrand-git
git pull
node ~/openaps-js/bin/pebble.js  glucose.json clock.json iob.json current_basal_profile.json currenttemp.json isf.json requestedtemp.json > /tmp/pebble-openaps.json
cat /tmp/pebble-openaps.json
jsonlint /tmp/pebble-openaps.json && cp /tmp/pebble-openaps.json /var/www/openaps.json 
cat /var/www/openaps.json
