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
    -n=*|--ns-host=*)
    NIGHTSCOUT_HOST="${i#*=}"
    shift # past argument=value
    ;;
    -a=*|--api-secret=*)
    API_SECRET="${i#*=}"
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
    echo "Usage: oref0-setup.sh <--dir=directory> <--serial=pump_serial_#> [--tty=/dev/ttySOMETHING] [--max_iob=0] [--ns-host=https://mynightscout.azurewebsites.net] [--api-secret=myplaintextsecret] [--cgm=G4]"
    read -p "Start interactive setup? [Y]/n " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        read -p "What would you like to call your loop directory? [myopenaps] " -r
        DIR=$REPLY
        if [[ -z $DIR ]]; then DIR="myopenaps"; fi
        echo "Ok, $DIR it is."
        directory="$(readlink -m $DIR)"
        read -p "What is your pump serial number? " -r
        serial=$REPLY
        echo "Ok, $serial it is."
        read -p "Are you using mmeowlink? If not, press enter. If so, what TTY port (i.e. /dev/ttySOMETHING)? " -r
        ttyport=$REPLY
        echo -n "Ok, "
        if [[ -z "$ttyport" ]]; then
            echo -n Carelink
        else
            echo -n TTY $ttyport
        fi
        echo " it is."
        echo Are you using Nightscout? If not, press enter.
        read -p "If so, what is your Nightscout host? (i.e. https://mynightscout.azurewebsites.net)? " -r
        NIGHTSCOUT_HOST=$REPLY
        if [[ -z "$ttyport" ]]; then
            echo Ok, no Nightscout for you.
        else
            echo "Ok, $NIGHTSCOUT_HOST it is."
        fi
        if [[ ! -z $NIGHTSCOUT_HOST ]]; then
            read -p "And what is your Nightscout api secret (i.e. myplaintextsecret)? " -r
            API_SECRET=$REPLY
            echo "Ok, $API_SECRET it is."
        fi
    fi
fi

#if [[ $# -gt 3 ]]; then
    #share_serial=$4
#fi

echo "Setting up oref0 in $directory"
echo -n "for pump $serial with Dexcom $CGM, NS host $NIGHTSCOUT_HOST, "
if [[ -z "$ttyport" ]]; then
    echo -n Carelink
else
    echo -n TTY $ttyport
fi
if [[ "$max_iob" -ne 0 ]]; then echo -n " and max_iob $max_iob"; fi
echo

read -p "Continue? y/[N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then

echo -n "Checking $directory: "
mkdir -p $directory
if ( cd $directory && git status 2>/dev/null >/dev/null && openaps use -h >/dev/null && echo true ); then
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

mkdir -p $HOME/src/
if [ -d "$HOME/src/oref0/" ]; then
    echo "$HOME/src/oref0/ already exists; pulling latest dev branch"
    (cd ~/src/oref0 && git fetch && git checkout dev && git pull) || die "Couldn't pull latest oref0 dev"
else
    echo -n "Cloning oref0 dev: "
    (cd ~/src && git clone -b dev git://github.com/openaps/oref0.git) || die "Couldn't clone oref0 dev"
fi
echo Checking oref0 installation
oref0-get-profile --exportDefaults 2>/dev/null >/dev/null || (echo Installing latest oref0 dev && cd $HOME/src/oref0/ && npm run global-install)

if [ -d "$HOME/src/mmeowlink/" ]; then
    echo "$HOME/src/mmeowlink/ already exists; pulling latest master branch"
    (cd ~/src/mmeowlink && git fetch && git checkout master && git pull) || die "Couldn't pull latest mmeowlink master"
else
    echo -n "Cloning mmeowlink master: "
    (cd ~/src && git clone -b master git://github.com/oskarpearson/mmeowlink.git) || die "Couldn't clone mmeowlink master"
fi
echo Checking mmeowlink installation
openaps vendor add --path . mmeowlink.vendors.mmeowlink 2>&1 | grep "No module" && (echo Installing latest mmeowlink master && cd $HOME/src/mmeowlink/ && sudo pip install -e .)

cd $directory
if [[ "$max_iob" -eq 0 ]]; then
    oref0-get-profile --exportDefaults > preferences.json || die "Could not run oref0-get-profile"
else
    echo "{ \"max_iob\": $max_iob }" > max_iob.json && oref0-get-profile --updatePreferences max_iob.json > preferences.json && rm max_iob.json || die "Could not run oref0-get-profile"
fi

cat preferences.json
git add preferences.json

sudo cp $HOME/src/oref0/logrotate.openaps /etc/logrotate.d/openaps || die "Could not cp /etc/logrotate.d/openaps"
sudo cp $HOME/src/oref0/logrotate.rsyslog /etc/logrotate.d/rsyslog || die "Could not cp /etc/logrotate.d/rsyslog"

test -d /var/log/openaps || sudo mkdir /var/log/openaps && sudo chown $USER /var/log/openaps || die "Could not create /var/log/openaps"

if [[ ! -z "$NIGHTSCOUT_HOST" && ! -z "$API_SECRET" ]]; then
    echo "Removing any existing ns device: "
    openaps device remove ns 2>/dev/null
    echo "Running nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET"
    nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET || die "Could not run nightscout autoconfigure-device-crud"
fi

# import template
for type in vendor device report alias; do
    echo importing $type file
    cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
done
#cat $HOME/src/oref0/lib/templates/refresh-loops.json | openaps import

# don't re-create devices if they already exist
openaps device show 2>/dev/null > /tmp/openaps-devices

# add devices
grep -q pump.ini .gitignore 2>/dev/null || echo pump.ini >> .gitignore
git add .gitignore
if [[ -z "$ttyport" ]]; then
    grep pump /tmp/openaps-devices || openaps device add pump medtronic $serial || die "Can't add pump"
    # carelinks can't listen for silence or mmtune, so just do a preflight check instead
    openaps alias add wait-for-silence 'report invoke monitor/temp_basal.json'
    openaps alias add wait-for-long-silence 'report invoke monitor/temp_basal.json'
    openaps alias add mmtune 'report invoke monitor/temp_basal.json'
else
    echo "Removing any existing pump device:"
    openaps device remove pump 2>/dev/null
    openaps device add pump mmeowlink subg_rfspy $ttyport $serial || die "Can't add pump"
    openaps alias add wait-for-silence '! bash -c "echo -n \"Listening: \"; for i in `seq 1 100`; do echo -n .; $HOME/src/mmeowlink/bin/mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 30 2>/dev/null | egrep -v subg | egrep No && break; done"'
    openaps alias add wait-for-long-silence '! bash -c "echo -n \"Listening: \"; for i in `seq 1 200`; do echo -n .; $HOME/src/mmeowlink/bin/mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 45 2>/dev/null | egrep -v subg | egrep No && break; done"'
fi


read -p "Schedule openaps in cron? y/[N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
# add crontab entries
(crontab -l; crontab -l | grep -q $NIGHTSCOUT_HOST || echo NIGHTSCOUT_HOST=$NIGHTSCOUT_HOST) | crontab -
(crontab -l; crontab -l | grep -q $API_SECRET || echo API_SECRET=`nightscout hash-api-secret $API_SECRET`) | crontab -
(crontab -l; crontab -l | grep -q PATH || echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin') | crontab -
(crontab -l; crontab -l | grep -q wpa_cli || echo '* * * * * sudo wpa_cli scan') | crontab -
(crontab -l; crontab -l | grep -q "killall -g --older-than 10m openaps" || echo '* * * * * killall -g --older-than 10m openaps') | crontab -
(crontab -l; crontab -l | grep -q "reset-git" || echo "* * * * * cd $directory && oref0-reset-git") | crontab -
(crontab -l; crontab -l | grep -q get-bg || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps get-bg' || ( date; openaps get-bg ; cat cgm/glucose.json | json -a sgv dateString | head -1 ) | tee -a /var/log/openaps/cgm-loop.log") | crontab -
(crontab -l; crontab -l | grep -q ns-loop || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps ns-loop' || openaps ns-loop | tee -a /var/log/openaps/ns-loop.log") | crontab -
(crontab -l; crontab -l | grep -q pump-loop || echo "* * * * * cd $directory && ( ps aux | grep -v grep | grep -q 'openaps pump-loop' || openaps pump-loop ) 2>&1 | tee -a /var/log/openaps/pump-loop.log") | crontab -
crontab -l
fi

fi

