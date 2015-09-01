#!/bin/bash
cd ~/openaps-dev
#git fetch --all && git reset --hard origin/master && git pull
#git pull
stat -c %y clock.json | cut -c 1-19
cat clock.json | sed 's/"//g' | sed 's/T/ /'
echo
#calculate-iob pumphistory.json profile.json clock.json > iob.json.new && grep iob iob.json.new && mv iob.json.new iob.json
node ~/openaps-js/bin/iob.js pumphistory.json profile.json clock.json > iob.json.new && grep iob iob.json.new && cp iob.json.new iob.json #&& git commit -m"iob found: committing" iob.json
#determine-basal iob.json currenttemp.json glucose.json profile.json > requestedtemp.json.new && grep temp requestedtemp.json.new && mv requestedtemp.json.new requestedtemp.json
#node ~/openaps-js/bin/determine-basal.js iob.json currenttemp.json glucose.json profile.json > requestedtemp.json.new && grep temp requestedtemp.json.new && cp requestedtemp.json.new requestedtemp.json #&& git commit -m"temp found: committing" requestedtemp.json
#git fetch origin master && git merge -X theirs origin/master && git push
#git pull && git push
node ~/openaps-js/bin/pebble.js  glucose.json clock.json iob.json current_basal_profile.json currenttemp.json isf.json requestedtemp.json > /tmp/pebble-openaps.json
cat /tmp/pebble-openaps.json
grep "refresh_frequency" /tmp/pebble-openaps.json && rsync -tuv /tmp/pebble-openaps.json www/openaps.json 
cat www/openaps.json
