#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

cd /home/pi/openaps-dev
git fetch --all
git reset --hard origin/master
git pull

#die() { echo "$@" 1>&2 ; exit 1; }
die() { echo "$@" ; exit 1; }

echo "Querying CGM"
openaps report invoke glucose.json || find glucose.json -mmin 10 || openaps report invoke glucose.json || die "Can't read from CGM"
git pull && git push
head -15 glucose.json

find *.json -mmin 15 -exec mv {} {}.old \;

# if it's been more than 3 minutes, unlock the CarelinkUSB
find /tmp/carelink.lock -mmin +3 -exec rm -f {} \; 2>/dev/null >/dev/null

# only one process can talk to the pump at a time
ls /tmp/carelink.lock >/dev/null 2>/dev/null && die "Carelink locked: exiting" && exit

echo "No lockfile: continuing"
touch /tmp/carelink.lock
/home/pi/decocare/insert.sh 2>/dev/null >/dev/null

function finish {
    rm /tmp/carelink.lock
}
trap finish EXIT

numprocs=$(fuser -n file $(python -m decocare.scan) 2>&1 | wc -l)
if [[ $numprocs -gt 0 ]] ; then
  die "Carelink USB already in use."
fi

echo "Checking pump status"
openaps status || openaps status || die "Can't get pump status"
echo "Querying pump"
openaps pumpquery || openaps pumpquery || die "Can't query pump" && git pull && git push

openaps suggest

tail clock.json
tail currenttemp.json
head -20 pumphistory.json

echo "Querying pump settings"
openaps pumpsettings || openaps pumpsettings || die "Can't query pump settings" && git pull && git push

openaps suggest || die "Can't calculate IOB or basal" && git pull && git push
tail profile.json
tail iob.json
tail requestedtemp.json

grep rate requestedtemp.json && ( openaps enact || openaps enact ) && tail enactedtemp.json
#openaps report invoke enactedtemp.json

#if /usr/bin/curl -sk https://diyps.net/closedloop.txt | /bin/grep set; then
    #echo "No lockfile: continuing"
    #touch /tmp/carelink.lock
    #/usr/bin/curl -sk https://diyps.net/closedloop.txt | while read x rate y dur op; do cat <<EOF
        #{ "duration": $dur, "rate": $rate, "temp": "absolute" }
#EOF
    #done | tee requestedtemp.json

    #openaps report invoke enactedtemp.json
#fi
        

rm /tmp/carelink.lock
