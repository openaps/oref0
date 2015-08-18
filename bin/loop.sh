#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

die() { echo "$@" ; exit 1; }

find /tmp/openaps.lock -mmin +10 -exec rm {} \; 2>/dev/null > /dev/null

# only one process can talk to the pump at a time
ls /tmp/openaps.lock >/dev/null 2>/dev/null && die "OpenAPS already running: exiting" && exit

echo "No lockfile: continuing"
touch /tmp/openaps.lock
~/decocare/insert.sh 2>/dev/null >/dev/null
python -m decocare.stick $(python -m decocare.scan) >/dev/null && echo "decocare.scan OK" || sudo ~/openaps-js/bin/fix-dead-carelink.sh

find ~/openaps-dev/.git/index.lock -mmin +5 -exec rm {} \; 2>/dev/null > /dev/null

function finish {
    rm /tmp/openaps.lock
}
trap finish EXIT

suggest() { find /tmp/openaps.online -mmin -10 | egrep -q '.*' && openaps suggest || openaps suggest-offline; }
getglucose() {
    echo "Querying CGM"
    openaps report invoke glucose.json.new || openaps report invoke glucose.json.new || share2-bridge file glucose.json.new
    grep glucose glucose.json.new && cp glucose.json.new glucose.json && git commit -m"glucose.json has glucose data: committing" glucose.json
}

findclock() { find clock.json -mmin -10 | egrep -q '.*'; }
findclocknew() { find clock.json.new -mmin -10 | egrep -q '.*'; }
findglucose() { find glucose.json -mmin -10 | egrep -q '.*'; }
findpumphistory() { find pumphistory.json -mmin -10 | egrep -q '.*'; }
findrequestedtemp() { find requestedtemp.json -mmin -10 | egrep -q '.*'; }

cd ~/openaps-dev && ( git status > /dev/null || ( mv ~/openaps-dev/.git /tmp/.git-`date +%s`; cd && openaps init openaps-dev && cd openaps-dev ) )
openaps report show > /dev/null || cp openaps.ini.bak openaps.ini


getglucose
head -15 glucose.json


numprocs=$(fuser -n file $(python -m decocare.scan) 2>&1 | wc -l)
if [[ $numprocs -gt 0 ]] ; then
  die "Carelink USB already in use or not available."
fi

echo "Checking pump status"
openaps status
grep -q status status.json.new && cp status.json.new status.json
echo "Querying pump"
openaps pumpquery || openaps pumpquery
findclocknew && grep T clock.json.new && cp clock.json.new clock.json
grep -q temp currenttemp.json.new && cp currenttemp.json.new currenttemp.json
grep -q timestamp pumphistory.json.new && cp pumphistory.json.new pumphistory.json
findclock && ~/bin/openaps-mongo.sh && touch /tmp/openaps.online

getglucose

~/openaps-js/bin/clockset.sh
suggest
findclock && findglucose && findpumphistory && findrequestedtemp && ~/openaps-js/bin/pebble.sh

tail clock.json
tail currenttemp.json

rm requestedtemp.json*
suggest || ( ~/openaps-js/bin/pumpsettings.sh && suggest ) || die "Can't calculate IOB or basal"
findclock && findglucose && findpumphistory && findrequestedtemp && ~/openaps-js/bin/pebble.sh
tail profile.json
tail iob.json
tail requestedtemp.json

findglucose && grep -q glucose glucose.json || die "No recent glucose data"
grep -q rate requestedtemp.json && ( openaps enact || openaps enact ) && tail enactedtemp.json

echo "Re-querying pump"
openaps pumpquery || openaps pumpquery
findclock '.*' && grep T clock.json.new && cp clock.json.new clock.json
grep -q temp currenttemp.json.new && cp currenttemp.json.new currenttemp.json
grep -q timestamp pumphistory.json.new && cp pumphistory.json.new pumphistory.json
rm /tmp/openaps.lock
findclock && findglucose && findpumphistory && findrequestedtemp && ~/openaps-js/bin/pebble.sh
findclock && ~/bin/openaps-mongo.sh && touch /tmp/openaps.online

ls /tmp/openaps.lock >/dev/null 2>/dev/null && die "OpenAPS already running: exiting" && exit
touch /tmp/openaps.lock
~/openaps-js/bin/pumpsettings.sh
