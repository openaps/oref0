#!/bin/bash
cd ~/openaps-dev
#eval `ssh-agent -s`
#ssh-add /home/sleibrand/.ssh/id_rsa.sleibrand-git
/usr/bin/git pull
/usr/bin/node ~/openaps-js/bin/pebble.js  glucose.json clock.json iob.json current_basal_profile.json currenttemp.json > pebble-openaps.json
cat pebble-openaps.json
/usr/bin/jsonlint pebble-openaps.json && cp pebble-openaps.json /var/www/openaps.json
cat /var/www/openaps.json
/usr/bin/git push
