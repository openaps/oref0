#!/bin/bash

# Attempt to read from a Carelink reader, upload data, and calculate the new
# glucose value.
#
# Released under MIT license. See the accompanying LICENSE.txt file for
# full terms and conditions
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

die() {
  echo "$@" | tee -a /var/log/openaps/easy.log
  exit 1
}

# TODO: allow openaps instances in directories other than ~/openaps-dev
# for now, make sure we're running in ~/openaps-dev/, or die.
cd ~/openaps-dev/ || die "can't cd ~/openaps-dev/"

# delete any recent-history json files older than 30m to make doubly sure we avoid using stale data
find pumphistory*.json* -mmin +30 -exec rm {} \; 2>/dev/null > /dev/null
find clock*.json* -mmin +30 -exec rm {} \; 2>/dev/null > /dev/null
find request*.json* -mmin +30 -exec rm {} \; 2>/dev/null > /dev/null
find current*temp*.json* -mmin +30 -exec rm {} \; 2>/dev/null > /dev/null
find glucose*.json* -mmin +30 -exec rm {} \; 2>/dev/null > /dev/null
find iob*.json* -mmin +30 -exec rm {} \; 2>/dev/null > /dev/null

# remove any old stale lockfiles
find /tmp/openaps.lock -mmin +10 -exec rm {} \; 2>/dev/null > /dev/null

# only one process can talk to the pump at a time
if ls /tmp/openaps.lock >/dev/null 2>/dev/null; then
    ls -la /tmp/openaps.lock
    echo "/tmp/openaps.lock exists"
    exit 1
fi

echo "No lockfile: continuing"
touch /tmp/openaps.lock
# if there are any old loops still running without proper lockfiles, kill them off
kill $(pgrep -f openaps-js/bin/loop.sh | grep -v ^$$\$)

# make sure decocare can talk to the Carelink USB stick
~/decocare/insert.sh 2>/dev/null >/dev/null
python -m decocare.stick $(python -m decocare.scan) >/dev/null && echo "decocare.scan OK" || sudo ~/openaps-js/bin/fix-dead-carelink.sh | tee -a /var/log/openaps/easy.log

# sometimes git gets stuck
find ~/openaps-dev/.git/index.lock -mmin +5 -exec rm {} \; 2>/dev/null > /dev/null
cd ~/openaps-dev && ( git status > /dev/null || ( mv ~/openaps-dev/.git /tmp/.git-`date +%s`; cd && openaps init openaps-dev && cd openaps-dev ) )
# sometimes openaps.ini gets truncated
openaps report show > /dev/null || cp openaps.ini.bak openaps.ini

function finish {
    rm /tmp/openaps.lock 2>/dev/null
}
trap finish EXIT

# define functions for everything we'll be doing

# get glucose data, either from attached CGM or from Share
getglucose() {
    echo "Querying CGM"
    ( ( openaps report invoke glucose.json.new || openaps report invoke glucose.json.new ) 2>/dev/null && grep -v '"glucose": 5' glucose.json.new | grep -q glucose ) || share2-bridge file glucose.json.new 2>/dev/null >/dev/null
    if diff -q glucose.json glucose.json.new; then
        echo No new glucose data
        return 1;
    else
        grep glucose glucose.json.new | head -1 | awk '{print $2}' | while read line; do echo -n " $line "; done >> /var/log/openaps/easy.log \
            && rsync -tu glucose.json.new glucose.json \
            #&& git commit -m"glucose.json has glucose data: committing" glucose.json 
        return 0;
    fi
}
# get pump status (suspended, etc.)
getpumpstatus() {
    echo "Checking pump status"
    openaps status 2>/dev/null || echo -n "!" >> /var/log/openaps/easy.log
    grep -q status status.json.new && ( rsync -tu status.json.new status.json && echo -n "." >> /var/log/openaps/easy.log ) || echo -n "!" >> /var/log/openaps/easy.log
}
# query pump, and update pump data files if successful
getcurrenttemp() {
    openaps report invoke currenttemp.json.new 2>/dev/null || ( echo -n "!" >> /var/log/openaps/easy.log && return 1 )
    grep -q temp currenttemp.json.new && ( rsync -tu currenttemp.json.new currenttemp.json && echo -n "." >> /var/log/openaps/easy.log ) || echo -n "!" >> /var/log/openaps/easy.log
}
querypump() {
    #openaps pumpquery 2>/dev/null || ( echo -n "!" >> /var/log/openaps/easy.log && return 1 )
    openaps report invoke clock.json.new 2>/dev/null || ( echo -n "!" >> /var/log/openaps/easy.log && return 1 )
    findclocknew && grep T clock.json.new && ( rsync -tu clock.json.new clock.json && echo -n "." >> /var/log/openaps/easy.log ) || echo -n "!" >> /var/log/openaps/easy.log
    getcurrenttemp || return 1
    openaps report invoke pumphistory.json.new 2>/dev/null || ( echo -n "!" >> /var/log/openaps/easy.log && return 1 )
    grep -q timestamp pumphistory.json.new && ( rsync -tu pumphistory.json.new pumphistory.json && echo -n "." >> /var/log/openaps/easy.log ) || echo -n "!" >> /var/log/openaps/easy.log
    upload
    return 0
}
# try to upload pumphistory data
upload() {
    if [ ! -z "$NIGHTSCOUT_HOST" ]; then
        ~/openaps-js/bin/ns-upload.sh
    fi
}
# if we haven't uploaded successfully in 10m, use offline mode (if no temp running, set current basal as temp to show the loop is working)
suggest() {
    openaps suggest || echo -n "!" >> /var/log/openaps/easy.log
    grep -q "too old" requestedtemp.online.json || ( find /tmp/openaps.online -mmin -10 | egrep -q '.*' && rsync -tu requestedtemp.online.json requestedtemp.json || rsync -tu requestedtemp.offline.json requestedtemp.json )
}
enact() {
    retries=5
    retry=0
    until openaps enact; do
        retry=`expr $retry + 1`
        echo "enact failed; retry $retry"
        if [ $retry -ge $retries ]; then bail "Failed to enact temp after $retries retries"; return $?; fi
        sleep 10;
    done
    if tail enactedtemp.json; then
        ( echo && cat enactedtemp.json | egrep -i "bg|dur|rate|re|tic|tim" | sort -r ) >> /var/log/openaps/easy.log 
        cat iob.json | json_pp | grep '"iob' >> /var/log/openaps/easy.log 
        if [ ! -z "$AZURE_SQL_API_HOST" ]; then
            send-tempbasal-Azure iob.json enactedtemp.json glucose.json $AZURE_SQL_API_HOST
        fi
        return 0
    fi
}
# get updated pump settings (basal schedules, targets, ISF, etc.)
getpumpsettings() { ~/openaps-js/bin/pumpsettings.sh; }

# functions for making sure we have up-to-date data before proceeding
findclock() { find clock.json -mmin -10 | egrep -q '.*'; }
findclocknew() { find clock.json.new -mmin -10 | egrep -q '.*'; }
findglucose() { find glucose.json -mmin -10 | egrep -q '.*'; }
findpumphistory() { find pumphistory.json -mmin -10 | egrep -q '.*'; }
findrequestedtemp() { find requestedtemp.json -mmin -10 | egrep -q '.*'; }
# write out current status to pebble.json
pebble() { ~/openaps-js/bin/pebble.sh; }

bail() {
  echo "$@" | tee -a /var/log/openaps/easy.log
  return 1
}

actionrequired() {
    # make sure we can still talk to the carelink stick
    python -m decocare.stick $(python -m decocare.scan) >/dev/null || sudo ~/openaps-js/bin/fix-dead-carelink.sh | tee -a /var/log/openaps/easy.log
    # if reservoir insulin remaining changes by more than 0.2U between runs, that probably indicates a bolus
    if awk '{getline t<"reservoir.json.new"; if (($0-t) > 0.2 || ($0-t < -0.2)) print "Reservoir changed from " $0 " to " t}' reservoir.json | grep changed; then
        echo "Reservoir status changed"
        rsync -tu reservoir.json.new reservoir.json
        return 0;
    else
        rsync -tu reservoir.json.new reservoir.json
        # if a temp is needed based on current BG and temp
        openaps report invoke requestedtemp.online.json || return 0
        grep rate requestedtemp.online.json
        return $?
    fi
}

execute() {
    getglucose
    head -15 glucose.json | grep -B1 glucose

    numprocs=$(fuser -n file $(python -m decocare.scan) 2>&1 | wc -l)
    if [[ $numprocs -gt 0 ]] ; then
        bail "Carelink USB already in use or not available."; return $?
    fi

    retries=5
    retry=0
    echo "Querying pump" && querypump 2>/dev/null
    until findpumphistory && findclock; do
        echo "Querying pump (try $retry)" && querypump 2>/dev/null
        retry=`expr $retry + 1`
        if [ $retry -ge $retries ]; then bail "Failed to query pump history after $retries retries"; return $?; fi
        sleep 30;
    done

    # get glucose again in case the pump queries took awhile
    getglucose

    # if we're offline, set the clock to the pump/CGM time
    ~/openaps-js/bin/clockset.sh

    # dump out a "what we're about to try to do" report
    suggest && pebble

    tail clock.json
    tail currenttemp.json

    # make sure we're not using an old suggestion
    rm requestedtemp* 2>/dev/null
    echo "Removing requestedtemp.json and recreating it"
    # if we can't run suggest, it might be because our pumpsettings are missing or screwed up"
    suggest || ( getpumpsettings && suggest ) || ( bail "Can't calculate IOB or basal"; return $? )
    pebble
    tail profile.json
    tail iob.json
    tail requestedtemp.json


    # don't act on stale glucose data
    findglucose && grep -q glucose glucose.json || ( bail "No recent glucose data"; return $? )
    # execute/enact the requested temp
    cat requestedtemp.json | json_pp | grep reason >> /var/log/openaps/easy.log
    if grep -q rate requestedtemp.json; then
        echo "Enacting temp"
        enact
    fi
}

requery() {
    numprocs=$(fuser -n file $(python -m decocare.scan) 2>&1 | wc -l)
    if [[ $numprocs -gt 0 ]] ; then
        bail "Carelink USB already in use or not available."; return $?
    fi

    echo "Re-querying pump"
    retries=5
    retry=0
    until querypump; do
        retry=`expr $retry + 1`
        echo "Re-query failed; retry $retry"
        if [ $retry -ge $retries ]; then bail "Failed to re-query pump"; return $?; fi
    done

    # unlock in case upload is really slow
    #rm /tmp/openaps.lock 2>/dev/null
    pebble
    upload

    # if another instance didn't start while we were uploading, refresh pump settings
    #ls /tmp/openaps.lock >/dev/null 2>/dev/null && die "OpenAPS already running: exiting" && exit
    touch /tmp/openaps.lock
    numprocs=$(fuser -n file $(python -m decocare.scan) 2>&1 | wc -l)
    if [[ $numprocs -gt 0 ]] ; then
        bail "Carelink USB already in use or not available."; return $?
    fi
    retries=2
    retry=0
    until getpumpsettings; do
        retry=`expr $retry + 1`
        echo "getpumpsettings failed; retry $retry"
        if [ $retry -ge $retries ]; then bail "getpumpsettings failed"; return $?; fi
    done
}

# main event loop

while(true); do 

    touch /tmp/openaps.lock
    # execute on startup, and then whenever actionrequired()
    until execute; do
        echo "Failed; retrying"
        sleep 5
    done
    requery
    getglucose && openaps report invoke requestedtemp.online.json && cat requestedtemp.online.json | json_pp | grep reason >> /var/log/openaps/easy.log
    # set a new reservoir baseline and watch for changes (boluses)
    openaps report invoke reservoir.json.new 2>/dev/null || echo -n "!" >> /var/log/openaps/easy.log && rsync -tu reservoir.json.new reservoir.json
    getcurrenttemp
    until actionrequired; do 
        touch /tmp/openaps.lock
        getglucose && openaps report invoke requestedtemp.online.json && cat requestedtemp.online.json | json_pp | grep reason >> /var/log/openaps/easy.log
        getcurrenttemp
        openaps report invoke reservoir.json.new 2>/dev/null || echo -n "!" >> /var/log/openaps/easy.log
        openaps report invoke clock.json.new 2>/dev/null || echo -n "!" >> /var/log/openaps/easy.log
        findclocknew && grep T clock.json.new && rsync -tu clock.json.new clock.json || echo -n "!" >> /var/log/openaps/easy.log
        pebble
        echo -n "-" >> /var/log/openaps/easy.log
        sleep 30
    done
done
