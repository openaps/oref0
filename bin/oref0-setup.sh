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

# defaults
max_iob=0
CGM="G4"
DIR=""
directory=""

for i in "$@"
do
case $i in
    -d=*|--dir=*)
    DIR="${i#*=}"
    # ~/ paths have to be expanded manually
    DIR="${DIR/#\~/$HOME}"
    directory="$(readlink -m $DIR)"
    shift # past argument=value
    ;;
    -s=*|--serial=*)
    serial="${i#*=}"
    shift # past argument=value
    ;;
    -t=*|--tty=*)
    ttyport="${i#*=}"
    shift # past argument=value
    ;;
    -m=*|--max_iob=*)
    max_iob="${i#*=}"
    shift # past argument=value
    ;;
    -c=*|--cgm=*)
    CGM="${i#*=}"
    shift # past argument=value
    ;;
    #--g5)
    #CGM="Dexcom_G5"
    #shift # past argument with no value
    #;;
    *)
            # unknown option
    echo "Option ${i#*=} unknown"
    ;;
esac
done

#if [[ $CGM != "G4" && $CGM != "G5" ]]; then
if [[ $CGM != "G4" ]]; then
    #echo "Unsupported CGM.  Please select (Dexcom) G4 (default) or G5."
    echo "This script only supports Dexcom G4 at the moment."
    echo "If you'd like to help add Dexcom G5 or Medtronic CGM support, please contact @scottleibrand on Gitter"
    echo
    DIR="" # to force a Usage prompt
fi
if [[ -z "$DIR" || -z "$serial" ]]; then
    die "Usage: oref0-setup.sh <--dir=directory> <--serial=pump_serial_#> [--tty=/dev/ttySOMETHING] [--max_iob=0] [--cgm=G4]"
fi

#if [[ $# -gt 3 ]]; then
    #share_serial=$4
#fi

echo "Setting up oref0 in $directory"
echo -n "for pump $serial with Dexcom $CGM, "
if [[ -z "$ttyport" ]]; then
    echo -n Carelink
else
    echo -n TTY $ttyport
fi
if [[ "$max_iob" -ne 0 ]]; then echo -n " and max_iob $max_iob"; fi
echo

read -p "Continue? " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then

echo -n Checking $directory:
mkdir -p $directory
if ( cd $directory && git status 2>/dev/null ); then
    echo $directory already exists
elif openaps init $directory; then
    echo $directory initialized
else
    die "Can't init $directory"
fi
cd $directory || die "Can't cd $directory"
ls monitor 2>/dev/null >/dev/null || mkdir monitor || die "Can't mkdir monitor"
ls raw-cgm 2>/dev/null >/dev/null || mkdir raw-cgm || die "Can't mkdir raw-cgm"
ls cgm 2>/dev/null >/dev/null || mkdir cgm || die "Can't mkdir cgm"
ls settings 2>/dev/null >/dev/null || mkdir settings || die "Can't mkdir settings"
ls enact 2>/dev/null >/dev/null || mkdir enact || die "Can't mkdir enact"
ls upload 2>/dev/null >/dev/null || mkdir upload || die "Can't mkdir upload"

if [[ "$max_iob" -eq 0 ]]; then
    oref0-get-profile --exportDefaults > preferences.json
else
    echo "{ \"max_iob\": $max_iob }" > max_iob.json && oref0-get-profile --updatePreferences max_iob.json > preferences.json && rm max_iob.json
fi

cat preferences.json
git add preferences.json

if [ -d "$HOME/src/oref0/" ]; then
    echo "$HOME/src/oref0/ already exists; pulling latest dev branch"
    #(cd ~/src/oref0 && git fetch && git checkout dev && git pull) || die "Couldn't pull latest oref0 dev"
    (cd ~/src/oref0 && git fetch && git checkout oref0-setup && git pull) || die "Couldn't pull latest oref0 oref0-setup"
else
    echo -n "Cloning oref0 dev: "
    cd ~/src && git clone -b dev git://github.com/openaps/oref0.git || die "Couldn't clone oref0 dev"
fi
if [ -d "$HOME/src/mmeowlink/" ]; then
    echo "$HOME/src/mmeowlink/ already exists; pulling latest master branch"
    (cd ~/src/mmeowlink && git fetch && git checkout master && git pull) || die "Couldn't pull latest mmeowlink master"
else
    echo -n "Cloning mmeowlink master: "
    cd ~/src && git clone -b master git://github.com/oskarpearson/mmeowlink.git || die "Couldn't clone mmeowlink master"
fi

sudo cp $HOME/src/oref0/logrotate.openaps /etc/logrotate.d/openaps
sudo cp $HOME/src/oref0/logrotate.rsyslog /etc/logrotate.d/rsyslog

test -d /var/log/openaps || sudo mkdir /var/log/openaps && sudo chown $USER /var/log/openaps

#openaps vendor add openapscontrib.timezones
#openaps vendor add mmeowlink.vendors.mmeowlink

#openaps vendor add openxshareble

# import template
cat $HOME/src/oref0/lib/templates/refresh-loops.json | openaps import

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
    openaps alias add wait-for-silence '! bash -c "echo -n \"Listening: \"; for i in `seq 1 100`; do echo -n .; $HOME/src/mmeowlink/bin/mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 30 2>/dev/null | egrep -v subg | egrep No && break; done"'
    openaps alias add wait-for-long-silence '! bash -c "echo -n \"Listening: \"; for i in `seq 1 100`; do echo -n .; $HOME/src/mmeowlink/bin/mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 45 2>/dev/null | egrep -v subg | egrep No && break; done"'
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

