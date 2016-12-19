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
EXTRAS=""

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
    -e=*|--enable=*)
    ENABLE="${i#*=}"
    shift # past argument=value
    ;;
    -b=*|--bleserial=*)
    BLE_SERIAL="${i#*=}"
    shift # past argument=value
    ;;
    *)
            # unknown option
    echo "Option ${i#*=} unknown"
    ;;
esac
done

if ! [[ ${CGM,,} =~ "g4" || ${CGM,,} =~ "g5" || ${CGM,,} =~ "mdt" || ${CGM,,} =~ "shareble" ]]; then
    echo "Unsupported CGM.  Please select (Dexcom) G4 (default), G5, or MDT."
    echo
    DIR="" # to force a Usage prompt
fi
if ! ( git config -l | grep -q user.email ) ; then
    read -p "What email address would you like to use for git commits? " -r
    EMAIL=$REPLY
    git config --global user.email $EMAIL
fi
if ! ( git config -l | grep -q user.name ); then
    read -p "What full name would you like to use for git commits? " -r
    NAME=$REPLY
    git config --global user.name $NAME
fi
if [[ -z "$DIR" || -z "$serial" ]]; then
    echo "Usage: oref0-setup.sh <--dir=directory> <--serial=pump_serial_#> [--tty=/dev/ttySOMETHING] [--max_iob=0] [--ns-host=https://mynightscout.azurewebsites.net] [--api-secret=myplaintextsecret] [--cgm=(G4|shareble|G5|MDT)] [--enable='autosens meal']"
    read -p "Start interactive setup? [Y]/n " -r
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        exit
    fi
    read -p "What would you like to call your loop directory? [myopenaps] " -r
    DIR=$REPLY
    if [[ -z $DIR ]]; then DIR="myopenaps"; fi
    echo "Ok, $DIR it is."
    directory="$(readlink -m $DIR)"
    read -p "What is your pump serial number (numbers only)? " -r
    serial=$REPLY
    echo "Ok, $serial it is."
    read -p "What kind of CGM are you using? (i.e. G4, ShareBLE, G5, MDT) " -r
    CGM=$REPLY
    echo "Ok, $CGM it is."
    if [[ ${CGM,,} =~ "shareble" ]]; then
        read -p "What is your G4 Share Serial Number? (i.e. SM12345678) " -r
        BLE_SERIAL=$REPLY
        echo "$BLE_SERIAL? Got it."
    fi
    read -p "Are you using mmeowlink? If not, press enter. If so, what TTY port (full port address, looks like "/dev/ttySOMETHING" without the quotes - you probably want to copy paste it)? " -r
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
    # remove any trailing / from NIGHTSCOUT_HOST
    NIGHTSCOUT_HOST=$(echo $REPLY | sed 's/\/$//g')
    if [[ -z $NIGHTSCOUT_HOST ]]; then
        echo Ok, no Nightscout for you.
    else
        echo "Ok, $NIGHTSCOUT_HOST it is."
    fi
    if [[ ! -z $NIGHTSCOUT_HOST ]]; then
        read -p "And what is your Nightscout api secret (i.e. myplaintextsecret)? " -r
        API_SECRET=$REPLY
        echo "Ok, $API_SECRET it is."
    fi
    read -p "Do you need any advanced features? y/[N] " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enable automatic sensitivity adjustment? y/[N] " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ENABLE+=" autosens "
        fi
        read -p "Enable advanced meal assist? y/[N] " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ENABLE+=" meal "
        fi
    fi
fi

echo -n "Setting up oref0 in $directory for pump $serial with $CGM CGM, "
if [[ ${CGM,,} =~ "shareble" ]]; then
    echo -n "G4 Share serial $BLE_SERIAL, "
fi
echo
echo -n "NS host $NIGHTSCOUT_HOST, "
if [[ -z "$ttyport" ]]; then
    echo -n Carelink
else
    echo -n TTY $ttyport
fi
if [[ "$max_iob" -ne 0 ]]; then echo -n ", max_iob $max_iob"; fi
if [[ ! -z "$ENABLE" ]]; then echo -n ", advanced features $ENABLE"; fi
echo

echo "To run again with these same options, use:"
echo -n "oref0-setup --dir=$directory --serial=$serial --cgm=$CGM"
if [[ ${CGM,,} =~ "shareble" ]]; then
    echo -n " --bleserial=$BLE_SERIAL"
fi
echo -n " --ns-host=$NIGHTSCOUT_HOST --api-secret=$API_SECRET"
if [[ ! -z "$ttyport" ]]; then
    echo -n " --tty=$ttyport"
fi
if [[ "$max_iob" -ne 0 ]]; then echo -n " --max_iob=$max_iob"; fi
if [[ ! -z "$ENABLE" ]]; then echo -n " --enable='$ENABLE'"; fi
echo; echo

read -p "Continue? y/[N] " -r
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
ls nightscout 2>/dev/null >/dev/null || mkdir nightscout || die "Can't mkdir nightscout"
ls raw-cgm 2>/dev/null >/dev/null || mkdir raw-cgm || die "Can't mkdir raw-cgm"
ls cgm 2>/dev/null >/dev/null || mkdir cgm || die "Can't mkdir cgm"
ls settings 2>/dev/null >/dev/null || mkdir settings || die "Can't mkdir settings"
ls enact 2>/dev/null >/dev/null || mkdir enact || die "Can't mkdir enact"
ls upload 2>/dev/null >/dev/null || mkdir upload || die "Can't mkdir upload"

mkdir -p $HOME/src/
if [ -d "$HOME/src/oref0/" ]; then
    echo "$HOME/src/oref0/ already exists; pulling latest"
    (cd ~/src/oref0 && git fetch && git pull) || die "Couldn't pull latest oref0"
else
    echo -n "Cloning oref0: "
    (cd ~/src && git clone git://github.com/openaps/oref0.git) || die "Couldn't clone oref0"
fi
echo Checking oref0 installation
npm list -g oref0 | egrep oref0@0.3. || (echo Installing latest oref0 && sudo npm install -g oref0)
#(echo Installing latest oref0 dev && cd $HOME/src/oref0/ && npm run global-install)

echo Checking mmeowlink installation
if openaps vendor add --path . mmeowlink.vendors.mmeowlink 2>&1 | grep "No module"; then
    echo Installing latest mmeowlink
    sudo pip install -U mmeowlink || die "Couldn't install mmeowlink"
fi

cd $directory || die "Can't cd $directory"
if [[ "$max_iob" -eq 0 ]]; then
    oref0-get-profile --exportDefaults > preferences.json || die "Could not run oref0-get-profile"
else
    echo "{ \"max_iob\": $max_iob }" > max_iob.json && oref0-get-profile --updatePreferences max_iob.json > preferences.json && rm max_iob.json || die "Could not run oref0-get-profile"
fi

cat preferences.json
git add preferences.json

# enable log rotation
sudo cp $HOME/src/oref0/logrotate.openaps /etc/logrotate.d/openaps || die "Could not cp /etc/logrotate.d/openaps"
sudo cp $HOME/src/oref0/logrotate.rsyslog /etc/logrotate.d/rsyslog || die "Could not cp /etc/logrotate.d/rsyslog"

test -d /var/log/openaps || sudo mkdir /var/log/openaps && sudo chown $USER /var/log/openaps || die "Could not create /var/log/openaps"

# configure ns
if [[ ! -z "$NIGHTSCOUT_HOST" && ! -z "$API_SECRET" ]]; then
    echo "Removing any existing ns device: "
    killall -g openaps 2>/dev/null; openaps device remove ns 2>/dev/null
    echo "Running nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET"
    nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET || die "Could not run nightscout autoconfigure-device-crud"
fi

# import template
for type in vendor device report alias; do
    echo importing $type file
    cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
done

# add/configure devices
if [[ ${CGM,,} =~ "g5" ]]; then
    openaps use cgm config --G5
    openaps report add raw-cgm/raw-entries.json JSON cgm oref0_glucose --hours "24.0" --threshold "100" --no-raw
elif [[ ${CGM,,} =~ "shareble" ]]; then
    echo Checking Adafruit_BluefruitLE installation
    if ! python -c "import Adafruit_BluefruitLE" 2>/dev/null; then
        if [ -d "$HOME/src/Adafruit_Python_BluefruitLE/" ]; then
            echo "$HOME/src/Adafruit_Python_BluefruitLE/ already exists; pulling latest master branch"
            (cd ~/src/Adafruit_Python_BluefruitLE && git fetch && git checkout wip/bewest/custom-gatt-profile && git pull) || die "Couldn't pull latest Adafruit_Python_BluefruitLE wip/bewest/custom-gatt-profile"
        else
            echo -n "Cloning Adafruit_Python_BluefruitLE wip/bewest/custom-gatt-profile: "
            (cd ~/src && git clone -b wip/bewest/custom-gatt-profile https://github.com/bewest/Adafruit_Python_BluefruitLE.git) || die "Couldn't clone Adafruit_Python_BluefruitLE wip/bewest/custom-gatt-profile"
        fi
        echo Installing Adafruit_BluefruitLE && cd $HOME/src/Adafruit_Python_BluefruitLE && sudo python setup.py develop || die "Couldn't install Adafruit_BluefruitLE"
    fi
    if [ -d "$HOME/src/openxshareble/" ]; then
        echo "$HOME/src/openxshareble/ already exists; pulling latest master branch"
        (cd ~/src/openxshareble && git fetch && git checkout master && git pull) || die "Couldn't pull latest openxshareble master"
    else
        echo -n "Cloning openxshareble master: "
        (cd ~/src && git clone https://github.com/openaps/openxshareble.git) || die "Couldn't clone openxshareble master"
    fi
    echo Checking openxshareble installation
    if ! python -c "import openxshareble" 2>/dev/null; then
        echo Installing openxshareble && (cd $HOME/src/openxshareble && sudo python setup.py develop) || die "Couldn't install openxshareble"
    fi
    sudo apt-get -y install libusb-dev libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev python-dbus || die "Couldn't apt-get install: run 'sudo apt-get update' and try again?"
    echo Checking bluez installation
    if ! bluetoothd --version | grep -q 5.37 2>/dev/null; then
        cd $HOME/src/ && wget https://www.kernel.org/pub/linux/bluetooth/bluez-5.37.tar.gz && tar xvfz bluez-5.37.tar.gz || die "Couldn't download bluez"
        cd $HOME/src/bluez-5.37 && ./configure --enable-experimental --disable-systemd && \
        make && sudo make install && sudo cp ./src/bluetoothd /usr/local/bin/ || die "Couldn't make bluez"
        sudo cp $HOME/src/openxshareble/bluetoothd.conf /etc/dbus-1/system.d/bluetooth.conf || die "Couldn't copy bluetoothd.conf"
        sudo killall bluetoothd; sudo /usr/local/bin/bluetoothd --experimental &
    fi
    openaps vendor add openxshareble || die "Couldn't add openxshareble vendor"
    openaps device remove cgm || die "Couldn't remove existing cgm device"
    openaps device add cgm openxshareble || die "Couldn't add openxshareble device"
    openaps use cgm configure --serial $BLE_SERIAL || die "Couldn't configure share serial"

fi
grep -q pump.ini .gitignore 2>/dev/null || echo pump.ini >> .gitignore
git add .gitignore
echo "Removing any existing pump device:"
killall -g openaps 2>/dev/null; openaps device remove pump 2>/dev/null

if [[ "$ttyport" =~ "spi" ]]; then
    echo Checking spi_serial installation
    if ! python -c "import spi_serial" 2>/dev/null; then
        if [ -d "$HOME/src/915MHzEdisonExplorer_SW/" ]; then
            echo "$HOME/src/915MHzEdisonExplorer_SW/ already exists; pulling latest master branch"
            (cd ~/src/915MHzEdisonExplorer_SW && git fetch && git checkout master && git pull) || die "Couldn't pull latest 915MHzEdisonExplorer_SW master"
        else
            echo -n "Cloning 915MHzEdisonExplorer_SW master: "
            (cd ~/src && git clone -b master https://github.com/EnhancedRadioDevices/915MHzEdisonExplorer_SW.git) || die "Couldn't clone 915MHzEdisonExplorer_SW master"
        fi
        echo Installing spi_serial && cd $HOME/src/915MHzEdisonExplorer_SW/spi_serial && sudo pip install -e . || die "Couldn't install spi_serial"
    fi

    echo Checking mraa installation
    if ! ldconfig -p | grep -q mraa; then
        echo Installing swig etc.
        sudo apt-get install -y libpcre3-dev git cmake python-dev swig || die "Could not install swig etc."

        if [ -d "$HOME/src/mraa/" ]; then
            echo "$HOME/src/mraa/ already exists; pulling latest master branch"
            (cd ~/src/mraa && git fetch && git checkout master && git pull) || die "Couldn't pull latest mraa master"
        else
            echo -n "Cloning mraa master: "
            (cd ~/src && git clone -b master https://github.com/intel-iot-devkit/mraa.git) || die "Couldn't clone mraa master"
        fi
        ( cd $HOME/src/ && mkdir -p mraa/build && cd $_ && cmake .. -DBUILDSWIGNODE=OFF && \
        make && sudo make install && echo && echo mraa installed. Please reboot before using. && echo ) || die "Could not compile mraa"
        sudo bash -c "grep -q i386-linux-gnu /etc/ld.so.conf || echo /usr/local/lib/i386-linux-gnu/ >> /etc/ld.so.conf && ldconfig" || die "Could not update /etc/ld.so.conf"
    fi

fi

cd $directory || die "Can't cd $directory"
if [[ -z "$ttyport" ]]; then
    openaps device add pump medtronic $serial || die "Can't add pump"
    # carelinks can't listen for silence or mmtune, so just do a preflight check instead
    openaps alias add wait-for-silence 'report invoke monitor/temp_basal.json'
    openaps alias add wait-for-long-silence 'report invoke monitor/temp_basal.json'
    openaps alias add mmtune 'report invoke monitor/temp_basal.json'
else
    openaps device add pump mmeowlink subg_rfspy $ttyport $serial || die "Can't add pump"
    openaps alias add wait-for-silence '! bash -c "(mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 1 | grep -q comms && echo -n Radio ok, || openaps mmtune) && echo -n \" Listening: \"; for i in $(seq 1 100); do echo -n .; mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 30 2>/dev/null | egrep -v subg | egrep No && break; done"'
    openaps alias add wait-for-long-silence '! bash -c "echo -n \"Listening: \"; for i in $(seq 1 200); do echo -n .; mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 45 2>/dev/null | egrep -v subg | egrep No && break; done"'
fi

# Medtronic CGM
if [[ ${CGM,,} =~ "mdt" ]]; then
    sudo pip install -U openapscontrib.glucosetools || die "Couldn't install glucosetools"
    openaps device remove cgm 2>/dev/null
    if [[ -z "$ttyport" ]]; then
        openaps device add cgm medtronic $serial || die "Can't add cgm"
    else
        openaps device add cgm mmeowlink subg_rfspy $ttyport $serial || die "Can't add cgm"
    fi
    for type in mdt-cgm; do
        echo importing $type file
        cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
    done
elif [[ ${CGM,,} =~ "G4" || ${CGM,,} =~ "shareble" ]]; then
    if [[ $ENABLE =~ "raw" ]]; then
        openaps report add raw-cgm/raw-entries.json JSON cgm oref0_glucose --hours "24" --threshold "100"
    fi
fi

# configure optional features
if [[ $ENABLE =~ autosens && $ENABLE =~ meal ]]; then
    EXTRAS="settings/autosens.json monitor/meal.json"
elif [[ $ENABLE =~ autosens ]]; then
    EXTRAS="settings/autosens.json"
elif [[ $ENABLE =~ meal ]]; then
    EXTRAS='"" monitor/meal.json'
fi

echo Running: openaps report add enact/suggested.json text determine-basal shell monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json $EXTRAS
openaps report add enact/suggested.json text determine-basal shell monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json $EXTRAS

echo
if [[ "$ttyport" =~ "spi" ]]; then
    echo Resetting spi_serial
    reset_spi_serial.py
fi
echo Attempting to communicate with pump:
openaps mmtune
echo

read -p "Schedule openaps in cron? y/[N] " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then
# add crontab entries
(crontab -l; crontab -l | grep -q "$NIGHTSCOUT_HOST" || echo NIGHTSCOUT_HOST=$NIGHTSCOUT_HOST) | crontab -
(crontab -l; crontab -l | grep -q "API_SECRET=" || echo API_SECRET=$(nightscout hash-api-secret $API_SECRET)) | crontab -
(crontab -l; crontab -l | grep -q "PATH=" || echo "PATH=$PATH" ) | crontab -
if [[ ${CGM,,} =~ "shareble" ]]; then
    # cross-platform hack to make sure experimental bluetoothd is running for openxshareble
    (crontab -l; crontab -l | grep -q "killall bluetoothd" || echo '@reboot sleep 30; sudo killall bluetoothd; sudo /usr/local/bin/bluetoothd --experimental; bluetooth_rfkill_event > /dev/null 2>&1') | crontab -
fi
(crontab -l; crontab -l | grep -q "sudo wpa_cli scan" || echo '* * * * * sudo wpa_cli scan') | crontab -
(crontab -l; crontab -l | grep -q "killall -g --older-than" || echo '* * * * * killall -g --older-than 15m openaps') | crontab -
# repair or reset git repository if it's corrupted or disk is full
(crontab -l; crontab -l | grep -q "cd $directory && oref0-reset-git" || echo "* * * * * cd $directory && oref0-reset-git") | crontab -
#truncate git history to 1000 commits if it has grown past 1500
(crontab -l; crontab -l | grep -q "cd $directory && oref0-truncate-git-history" || echo "* * * * * cd $directory && oref0-truncate-git-history") | crontab -
if ! [[ ${CGM,,} =~ "mdt" ]]; then
    (crontab -l; crontab -l | grep -q "cd $directory && ps aux | grep -v grep | grep -q 'openaps get-bg'" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps get-bg' || ( date; openaps get-bg ; cat cgm/glucose.json | json -a sgv dateString | head -1 ) | tee -a /var/log/openaps/cgm-loop.log") | crontab -
fi
(crontab -l; crontab -l | grep -q "cd $directory && ps aux | grep -v grep | grep -q 'openaps ns-loop'" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps ns-loop' || openaps ns-loop | tee -a /var/log/openaps/ns-loop.log") | crontab -
if [[ $ENABLE =~ autosens ]]; then
    (crontab -l; crontab -l | grep -q "cd $directory && ps aux | grep -v grep | grep -q 'openaps autosens'" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps autosens' || openaps autosens | tee -a /var/log/openaps/autosens-loop.log") | crontab -
fi
if [[ "$ttyport" =~ "spi" ]]; then
    (crontab -l; crontab -l | grep -q "cd $directory && reset_spi_serial.py" || echo "@reboot cd $directory && reset_spi_serial.py") | crontab -
fi
(crontab -l; crontab -l | grep -q "cd $directory && ( ps aux | grep -v grep | grep -q 'openaps pump-loop'" || echo "* * * * * cd $directory && ( ps aux | grep -v grep | grep -q 'openaps pump-loop' || openaps pump-loop ) 2>&1 | tee -a /var/log/openaps/pump-loop.log") | crontab -
crontab -l

if [[ ${CGM,,} =~ "shareble" ]]; then
    echo
    echo "To pair your G4 Share receiver, open its Setttings, select Share, Forget Device (if previously paired), then turn sharing On"
fi

fi

fi

