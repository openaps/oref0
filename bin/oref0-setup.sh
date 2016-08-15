#!/bin/bash

# This script sets up an openaps environment to work with loop.sh,
# by defining the required devices, reports, and aliases.
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

die() {
  echo "$@"
  exit 1
}

if [[ $# -lt 2 ]]; then
    #openaps device show pump 2>/dev/null >/dev/null || die "Usage: setup.sh <directory> <pump serial #> [max_iob] [Share serial #]
    openaps device show pump 2>/dev/null >/dev/null || die "Usage: setup.sh <directory> <pump serial #> [/dev/ttySOMETHING] [max_iob]"
fi
directory=`mkdir -p $1; cd $1; pwd`
serial=$2

ttyport=$3

if [[ $# -lt 4 ]]; then
    max_iob=0
else
    max_iob=$4
fi

#if [[ $# -gt 3 ]]; then
    #share_serial=$4
#fi

echo -n "Setting up oref0 in $directory for pump $serial with "
if [[ $# -lt 3 ]]; then
    echo -n Carelink
else
    echo -n TTY $ttyport
fi
if [[ $# -ge 4 ]]; then echo -n " and max_iob $max_iob"; fi
echo

read -p "Continue? " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then

( ( cd $directory 2>/dev/null && git status ) || ( openaps init $directory ) ) || die "Can't init $directory"
cd $directory || die "Can't cd $directory"
ls monitor 2>/dev/null >/dev/null || mkdir monitor || die "Can't mkdir monitor"
ls raw-cgm 2>/dev/null >/dev/null || mkdir raw-cgm || die "Can't mkdir raw-cgm"
ls cgm 2>/dev/null >/dev/null || mkdir cgm || die "Can't mkdir cgm"
ls settings 2>/dev/null >/dev/null || mkdir settings || die "Can't mkdir settings"
ls enact 2>/dev/null >/dev/null || mkdir enact || die "Can't mkdir enact"
ls upload 2>/dev/null >/dev/null || mkdir upload || die "Can't mkdir upload"

if [[ $# -lt 4 ]]; then
    oref0-get-profile --exportDefaults > preferences.json
else
    echo "{ \"max_iob\": $max_iob }" > max_iob.json && oref0-get-profile --updatePreferences max_iob.json > preferences.json && rm max_iob.json
fi

cat preferences.json
git add preferences.json

sudo cp ~/src/oref0/logrotate.openaps /etc/logrotate.d/openaps
sudo cp ~/src/oref0/logrotate.rsyslog /etc/logrotate.d/rsyslog

test -d /var/log/openaps || sudo mkdir /var/log/openaps && sudo chown $USER /var/log/openaps

#openaps vendor add openapscontrib.timezones
#openaps vendor add mmeowlink.vendors.mmeowlink

#openaps vendor add openxshareble

# import template
cat ~/src/oref0/lib/templates/refresh-loops.json | openaps import

# don't re-create devices if they already exist
openaps device show 2>/dev/null > /tmp/openaps-devices

# add devices
grep -q pump.ini .gitignore 2>/dev/null || echo pump.ini >> .gitignore
git add .gitignore
if [[ $# -lt 3 ]]; then
    grep pump /tmp/openaps-devices || openaps device add pump medtronic $serial || die "Can't add pump"
    # carelinks can't listen for silence or mmtune, so just do a preflight check instead
    openaps alias add wait-for-silence 'report invoke monitor/temp_basal.json'
    openaps alias add wait-for-long-silence 'report invoke monitor/temp_basal.json'
    openaps alias add mmtune 'report invoke monitor/temp_basal.json'
else
    grep pump /tmp/openaps-devices || openaps device add pump mmeowlink subg_rfspy $ttyport $serial || die "Can't add pump"
    openaps alias add wait-for-silence '! bash -c "echo -n \"Listening: \"; for i in `seq 1 100`; do echo -n .; ~/src/mmeowlink/bin/mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 30 2>/dev/null | egrep -v subg | egrep No && break; done"'
    openaps alias add wait-for-long-silence '! bash -c "echo -n \"Listening: \"; for i in `seq 1 100`; do echo -n .; ~/src/mmeowlink/bin/mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 45 2>/dev/null | egrep -v subg | egrep No && break; done"'
fi


read -p "Schedule openaps in cron? " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
# add crontab entries
(crontab -l; crontab -l | grep -q PATH || echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin') | crontab -
(crontab -l; crontab -l | grep -q killall || echo '* * * * * killall -g --older-than 10m openaps') | crontab -
(crontab -l; crontab -l | grep -q "reset-git" || echo "* * * * * cd $directory && oref0-reset-git") | crontab -
(crontab -l; crontab -l | grep -q get-bg || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps get-bg' || ( date; openaps get-bg ; cat cgm/glucose.json | json -a sgv dateString | head -1 ) | tee -a /var/log/openaps/cgm-loop.log") | crontab -
(crontab -l; crontab -l | grep -q ns-loop || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps ns-loop' || openaps ns-loop | tee -a /var/log/openaps/ns-loop.log") | crontab -
(crontab -l; crontab -l | grep -q pump-loop || echo "* * * * * cd $directory && ( ps aux | grep -v grep | grep -q 'openaps pump-loop' || openaps pump-loop ) 2>&1 | tee -a /var/log/openaps/pump-loop.log") | crontab -
crontab -l
fi

fi

