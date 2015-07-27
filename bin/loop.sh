#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

die() { echo "$@" ; exit 1; }

# only one process can talk to the pump at a time
ls /tmp/openaps.lock >/dev/null 2>/dev/null && die "OpenAPS already running: exiting" && exit

echo "No lockfile: continuing"
touch /tmp/openaps.lock
/home/pi/decocare/insert.sh 2>/dev/null >/dev/null

find /tmp/openaps.lock -mmin +5 -exec rm {} \;
find /home/pi/openaps-dev/.git/index.lock -mmin +5 -exec rm {} \;

function finish {
    rm /tmp/openaps.lock
}
trap finish EXIT

cd /home/pi/openaps-dev
#git fetch --all && ( git pull --ff-only || ( echo "Can't pull ff: resetting" && git reset --hard origin/master ) )
#git fetch origin master && ( git merge -X theirs origin/master || git reset --hard origin/master )


echo "Querying CGM"
openaps report invoke glucose.json.new || openaps report invoke glucose.json.new 
grep glucose glucose.json.new && cp glucose.json.new glucose.json && git commit -m"glucose.json has glucose data: committing" glucose.json
#git fetch origin master && git merge -X ours origin/master && git push
#git pull && git push
#grep glucose glucose.json || git reset --hard origin/master
head -15 glucose.json


numprocs=$(fuser -n file $(python -m decocare.scan) 2>&1 | wc -l)
if [[ $numprocs -gt 0 ]] ; then
  die "Carelink USB already in use."
fi

echo "Checking pump status"
openaps status
#openaps status || openaps status || die "Can't get pump status"
grep -q status status.json.new && cp status.json.new status.json
#git fetch origin master && git merge -X ours origin/master && git push
#git pull && git push
echo "Querying pump"
#openaps pumpquery || openaps pumpquery || die "Can't query pump" && git pull && git push
openaps pumpquery || openaps pumpquery
find clock.json.new -mmin -10 | egrep -q '.*' && grep T clock.json.new && cp clock.json.new clock.json
grep -q temp currenttemp.json.new && cp currenttemp.json.new currenttemp.json
grep -q timestamp pumphistory.json.new && cp pumphistory.json.new pumphistory.json
find clock.json -mmin -5 | egrep -q '.*' && ~/bin/openaps-mongo.sh
#git fetch origin master && git merge -X ours origin/master && git push
#git pull && git push

echo "Querying CGM"
openaps report invoke glucose.json.new || openaps report invoke glucose.json.new 
grep glucose glucose.json.new && cp glucose.json.new glucose.json && git commit -m"glucose.json has glucose data: committing" glucose.json
#git fetch origin master && git merge -X ours origin/master && git push
#git pull && git push

openaps suggest
#git fetch origin master && git merge -X ours origin/master && git push
#git pull && git push

tail clock.json
tail currenttemp.json
#head -20 pumphistory.json

echo "Querying pump settings"
openaps pumpsettings || openaps pumpsettings # || die "Can't query pump settings" # && git pull && git push
grep -q insulin_action_curve pump_settings.json.new && cp pump_settings.json.new pump_settings.json
grep -q "mg/dL" bg_targets.json.new && cp bg_targets.json.new bg_targets.json
grep -q sensitivity isf.json.new && cp isf.json.new isf.json
grep -q rate current_basal_profile.json.new && cp current_basal_profile.json.new current_basal_profile.json
grep -q grams carb_ratio.json.new && cp carb_ratio.json.new carb_ratio.json

rm requestedtemp.json*
openaps suggest || die "Can't calculate IOB or basal"
#git fetch origin master && git merge -X ours origin/master && git push
#git pull && git push
tail profile.json
tail iob.json
tail requestedtemp.json

#openaps report invoke enactedtemp.json
find glucose.json -mmin -10 | egrep -q '.*' && grep -q glucose glucose.json || die "No recent glucose data"
grep -q rate requestedtemp.json && ( openaps enact || openaps enact ) && tail enactedtemp.json
#git fetch origin master && git merge -X ours origin/master && git push
#git pull && git push

#if /usr/bin/curl -sk https://diyps.net/closedloop.txt | /bin/grep set; then
    #echo "No lockfile: continuing"
    #touch /tmp/carelink.lock
    #/usr/bin/curl -sk https://diyps.net/closedloop.txt | while read x rate y dur op; do cat <<EOF
        #{ "duration": $dur, "rate": $rate, "temp": "absolute" }
#EOF
    #done | tee requestedtemp.json

    #openaps report invoke enactedtemp.json
#fi
        

echo "Re-querying pump"
#openaps pumpquery || openaps pumpquery || die "Can't query pump" && git pull && git push
openaps pumpquery || openaps pumpquery
find clock.json.new -mmin -10 | egrep -q '.*' && grep T clock.json.new && cp clock.json.new clock.json
grep -q temp currenttemp.json.new && cp currenttemp.json.new currenttemp.json
grep -q timestamp pumphistory.json.new && cp pumphistory.json.new pumphistory.json
rm /tmp/openaps.lock
find clock.json -mmin -5 | egrep -q '.*' && ~/bin/openaps-mongo.sh
