#!/bin/bash

# This script sets up a read-only openaps environment that uploads pump history data to nightscout
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

self=$(basename $0)

function usage ( ) {

cat <<EOF
$self <directory> <serial> <??> <diyps_url>
$self - setup uploading to NS?
EOF
}

case "$1" in
  --help|help|-h)
    usage
    exit 0
    ;;
esac

if [[ $# -lt 2 ]]; then
    openaps device show pump 2>/dev/null >/dev/null || die "Usage: $self <directory> <pump serial #>"
fi
directory=`mkdir -p $1; cd $1; pwd`
serial=$2

echo -n Setting up oref0 in $directory for pump $serial

if [[ $# -gt 3 ]]; then
	diyps_url=$4
    echo -n ", DIYPS URL $diyps_url"
fi
echo

read -p "Continue? " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then

( ( cd $directory 2>/dev/null && git status ) || ( openaps init $directory ) ) || die "Can't init $directory"
cd $directory || die "Can't cd $directory"

#sudo cp ~/src/oref0/logrotate.openaps /etc/logrotate.d/openaps
sudo bash -c "curl -s https://raw.githubusercontent.com/openaps/oref0/master/logrotate.openaps > /etc/logrotate.d/openaps"
#sudo cp ~/src/oref0/logrotate.rsyslog /etc/logrotate.d/rsyslog
sudo bash -c "curl -s https://raw.githubusercontent.com/openaps/oref0/master/logrotate.rsyslog > /etc/logrotate.d/rsyslog"

test -d /var/log/openaps || sudo mkdir /var/log/openaps && sudo chown $USER /var/log/openaps

openaps vendor add openapscontrib.timezones

# don't re-create devices if they already exist
openaps device show 2>/dev/null > /tmp/openaps-devices

# add devices
grep -q pump.ini .gitignore 2>/dev/null || echo pump.ini >> .gitignore
git add .gitignore
grep pump /tmp/openaps-devices || openaps device add pump medtronic $serial || die "Can't add pump"
grep cgm /tmp/openaps-devices || openaps device add cgm dexcom || die "Can't add CGM"
git add cgm.ini
grep ns-glucose /tmp/openaps-devices || openaps device add ns-glucose process 'bash -c "curl -s $NIGHTSCOUT_HOST/api/v1/entries/sgv.json | json -e \"this.glucose = this.sgv\""' || die "Can't add ns-glucose"
git add ns-glucose.ini
grep oref0 /tmp/openaps-devices || openaps device add oref0 process oref0 || die "Can't add oref0"
git add oref0.ini
grep iob /tmp/openaps-devices || openaps device add iob process --require "pumphistory profile clock" oref0 calculate-iob || die "Can't add iob"
git add iob.ini
grep tz /tmp/openaps-devices || openaps device add tz timezones || die "Can't add tz"
git add tz.ini
#grep latest-treatments /tmp/openaps-devices || openaps device add latest-treatments process nightscout 'latest-openaps-treatment $NIGHTSCOUT_HOST' || die "Can't add latest-treatments"
#git add latest-treatments.ini

# don't re-create reports if they already exist
openaps report show 2>/dev/null > /tmp/openaps-reports

# add reports for frequently-refreshed monitoring data
ls monitor 2>/dev/null >/dev/null || mkdir monitor || die "Can't mkdir monitor"
grep monitor/glucose.json /tmp/openaps-reports || openaps report add monitor/glucose.json JSON cgm iter_glucose 5 || die "Can't add glucose.json"
grep monitor/ns-glucose.json /tmp/openaps-reports || openaps report add monitor/ns-glucose.json text ns-glucose shell || die "Can't add ns-glucose.json"
grep settings/model.json /tmp/openaps-reports || openaps report add settings/model.json JSON pump model || die "Can't add model"
grep monitor/clock.json /tmp/openaps-reports || openaps report add monitor/clock.json JSON pump read_clock || die "Can't add clock.json"
grep monitor/clock-zoned.json /tmp/openaps-reports || openaps report add monitor/clock-zoned.json JSON tz clock monitor/clock.json || die "Can't add clock-zoned.json"
grep monitor/temp_basal.json /tmp/openaps-reports || openaps report add monitor/temp_basal.json JSON pump read_temp_basal || die "Can't add temp_basal.json"
grep monitor/reservoir.json /tmp/openaps-reports || openaps report add monitor/reservoir.json JSON pump reservoir || die "Can't add reservoir.json"
grep monitor/pumphistory.json /tmp/openaps-reports || openaps report add monitor/pumphistory.json JSON pump iter_pump_hours 4 || die "Can't add pumphistory.json"
grep monitor/pumphistory-zoned.json /tmp/openaps-reports || openaps report add monitor/pumphistory-zoned.json JSON tz rezone monitor/pumphistory.json || die "Can't add pumphistory-zoned.json"
grep monitor/iob.json /tmp/openaps-reports || openaps report add monitor/iob.json text iob shell monitor/pumphistory-zoned.json settings/profile.json monitor/clock-zoned.json || die "Can't add iob.json"

# add reports for infrequently-refreshed settings data
ls settings 2>/dev/null >/dev/null || mkdir settings || die "Can't mkdir settings"
grep settings/bg_targets.json /tmp/openaps-reports || openaps report add settings/bg_targets.json JSON pump read_bg_targets || die "Can't add bg_targets.json"
grep settings/insulin_sensitivities.json /tmp/openaps-reports || openaps report add settings/insulin_sensitivities.json JSON pump read_insulin_sensitivities || die "Can't add insulin_sensitivities.json"
grep settings/basal_profile.json /tmp/openaps-reports || openaps report add settings/basal_profile.json JSON pump read_selected_basal_profile || die "Can't add basal_profile.json"
grep settings/settings.json /tmp/openaps-reports || openaps report add settings/settings.json JSON pump read_settings || die "Can't add settings.json"

# add aliases to get data
openaps alias add invoke "report invoke" || die "Can't add invoke"
openaps alias add preflight '! bash -c "rm -f monitor/clock.json && openaps report invoke monitor/clock.json >/dev/null 2>/dev/null && grep -q T monitor/clock.json && echo PREFLIGHT OK || ( mm-stick warmup || sudo oref0-reset-usb; echo PREFLIGHT FAIL; sleep 120; exit 1 )"' || die "Can't add preflight"
openaps alias add monitor-cgm "report invoke monitor/glucose.json" || die "Can't add monitor-cgm"
openaps alias add get-ns-glucose "report invoke monitor/ns-glucose.json" || die "Can't add get-ns-glucose"
openaps alias add monitor-pump "report invoke monitor/clock.json monitor/temp_basal.json monitor/pumphistory.json monitor/pumphistory-zoned.json monitor/clock-zoned.json" || die "Can't add monitor-pump"
openaps alias add get-settings "report invoke settings/model.json settings/bg_targets.json settings/insulin_sensitivities.json settings/basal_profile.json settings/settings.json" || die "Can't add get-settings"
openaps alias add get-bg '! bash -c "openaps monitor-cgm 2>/dev/null || ( openaps get-ns-glucose && grep -q glucose monitor/ns-glucose.json && mv monitor/ns-glucose.json monitor/glucose.json )"' || die "Can't add get-bg"
openaps alias add gather '! bash -c "rm monitor/*; ( openaps get-bg && openaps get-settings >/dev/null && openaps monitor-pump ) 2>/dev/null"' || die "Can't add gather"
openaps alias add wait-for-bg '! bash -c "touch monitor/glucose.json; cp monitor/glucose.json monitor/last-glucose.json; while(diff -q monitor/last-glucose.json monitor/glucose.json); do echo -n .; sleep 10; openaps get-bg >/dev/null; done"'

# upload treatments to nightscout
ls upload 2>/dev/null >/dev/null || mkdir upload || die "Can't mkdir upload"
openaps alias add latest-ns-treatment-time '! bash -c "nightscout latest-openaps-treatment $NIGHTSCOUT_HOST | json created_at"' || die "Can't add latest-ns-treatment-time"
openaps alias add format-latest-nightscout-treatments '! bash -c "nightscout cull-latest-openaps-treatments monitor/pumphistory-zoned.json settings/model.json $(openaps latest-ns-treatment-time) > upload/latest-treatments.json"' || die "Can't add format-latest-nightscout-treatments"
openaps alias add upload-recent-treatments '! bash -c "openaps format-latest-nightscout-treatments && test $(json -f upload/latest-treatments.json -a created_at eventType | wc -l ) -gt 0 && (ns-upload $NIGHTSCOUT_HOST $API_SECRET treatments.json upload/latest-treatments.json ) || echo \"No recent treatments to upload\""' || die "Can't add upload-recent-treatments"
openaps alias add upload '! bash -c "openaps preflight && ( openaps monitor-pump && openaps upload-recent-treatments && openaps get-settings) 2>/dev/null >/dev/null && echo -n \"Uploaded; most recent treatment event @ \" && openaps latest-ns-treatment-time || echo \"Error; could not upload\""' || die "Can't add upload"

read -p "Schedule oref1 (openaps nightscout uploader) in cron? " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Nightscout hostname? "
    NIGHTSCOUT_HOST=$REPLY
    read -p "Hashed API secret? "
    API_SECRET=$REPLY
    read -p "Upload to $NIGHTSCOUT_HOST using API secret $API_SECRET, correct? " -n 1 -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        (crontab -l; echo NIGHTSCOUT_HOST=$NIGHTSCOUT_HOST) | crontab -
        (crontab -l; echo API_SECRET=$API_SECRET) | crontab -
    fi
    # add crontab entries
    (crontab -l; crontab -l | grep -q PATH || echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin') | crontab -
    (crontab -l; crontab -l | grep -q killall || echo '* * * * * killall -g --older-than 10m openaps') | crontab -
    (crontab -l; crontab -l | grep -q "reset-git" || echo "* * * * * cd $directory && oref0-reset-git") | crontab -
    (crontab -l; crontab -l | grep -q uploader || echo "* * * * * cd $directory && ( ps aux | grep -v grep | grep -q 'openaps ' && echo OpenAPS already running || openaps upload ) 2>&1 | tee -a /var/log/openaps/uploader.log") | crontab -
    crontab -l
fi

fi
