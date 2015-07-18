#!/bin/bash
cd ~/openaps-dev
#eval `ssh-agent -s`
#ssh-add /home/sleibrand/.ssh/id_rsa.sleibrand-git
git pull
stat -c %y clock.json | cut -c 1-19
cat clock.json | sed 's/"//g' | sed 's/T/ /'
echo
calculate-iob pumphistory.json profile.json clock.json > iob.json.new && grep iob iob.json.new && mv iob.json.new iob.json
determine-basal iob.json currenttemp.json glucose.json profile.json > requestedtemp.json.new && grep temp requestedtemp.json.new && mv requestedtemp.json.new requestedtemp.json
node ~/openaps-js/bin/pebble.js  glucose.json clock.json iob.json current_basal_profile.json currenttemp.json isf.json requestedtemp.json > /tmp/pebble-openaps.json
cat /tmp/pebble-openaps.json
jsonlint /tmp/pebble-openaps.json && cp /tmp/pebble-openaps.json /var/www/openaps.json 
cat /var/www/openaps.json
