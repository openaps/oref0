#!/bin/bash

# This script sets up an openaps environment by defining the required devices,
# reports, and aliases, and optionally enabling it in cron.
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
CGM="G4-upload"
DIR=""
directory=""
EXTRAS=""
radio_locale="US"

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
    -rl=*|--radio_locale=*)
    radio_locale="${i#*=}"
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
    -mdsm=*|--max_daily_safety_multiplier=*)
    max_daily_safety_multiplier="${i#*=}"
    shift # past argument=value
    ;;
    -cbsm=*|--current_basal_safety_multiplier=*)
    current_basal_safety_multiplier="${i#*=}"
    shift # past argument=value
    ;;
    -bdd=*|--bolussnooze_dia_divisor=*)
    bolussnooze_dia_divisor="${i#*=}"
    shift # past argument=value
    ;;
    -m5c=*|--min_5m_carbimpact=*)
    min_5m_carbimpact="${i#*=}"
    shift # past argument=value
    ;;
    -c=*|--cgm=*)
    CGM="${i#*=}"
    shift # past argument=value
    ;;
    -n=*|--ns-host=*)
    NIGHTSCOUT_HOST=$(echo ${i#*=} | sed 's/\/$//g')
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
    -l=*|--blemac=*)
    BLE_MAC="${i#*=}"
    shift # past argument=value
    ;;
    --btmac=*)
    BT_MAC="${i#*=}"
    shift # past argument=value
    ;;
    -p=*|--btpeb=*)
    BT_PEB="${i#*=}"
    shift # past argument=value
    ;;
    --ww_ti_usb_reset=*) # use reset if pump device disappears with TI USB and WW-pump
    WW_TI_USB_RESET="${i#*=}"
    shift # past argument=value
    ;;
    *)
            # unknown option
    echo "Option ${i#*=} unknown"
    ;;
esac
done

if ! [[ ${CGM,,} =~ "g4-upload" || ${CGM,,} =~ "g5" || ${CGM,,} =~ "mdt" || ${CGM,,} =~ "shareble" || ${CGM,,} =~ "xdrip" || ${CGM,,} =~ "g4-local" ]]; then
    echo "Unsupported CGM.  Please select (Dexcom) G4-upload (default), G4-local-only, G5, MDT or xdrip."
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
    echo "Usage: oref0-setup.sh <--dir=directory> <--serial=pump_serial_#> [--tty=/dev/ttySOMETHING] [--max_iob=0] [--ns-host=https://mynightscout.azurewebsites.net] [--api-secret=myplaintextsecret] [--cgm=(G4-upload|G4-local-only|shareble|G5|MDT|xdrip)] [--bleserial=SM123456] [--blemac=FE:DC:BA:98:76:54] [--btmac=AB:CD:EF:01:23:45] [--enable='autosens meal dexusb'] [--radio_locale=(WW|US)] [--ww_ti_usb_reset=(yes|no)]"
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
    read -p "What kind of CGM are you using? (e.g., G4-upload, G4-local-only, G5, MDT, xdrip?) Note: G4-local-only will NOT upload BGs from a plugged in receiver to Nightscout" -r
    CGM=$REPLY
    echo "Ok, $CGM it is."
    if [[ ${CGM,,} =~ "shareble" ]]; then
        read -p "What is your G4 Share Serial Number? (i.e. SM12345678) " -r
        BLE_SERIAL=$REPLY
        echo "$BLE_SERIAL? Got it."
    fi


    read -p "Are you using an Explorer Board? y/[N] " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ttyport=/dev/spidev5.1
    echo "Ok, yay for Explorer Board! "
    else
        read -p 'Are you using mmeowlink (i.e. with a TI stick)? If not, press enter. If so, what TTY port (full port address, looks like "/dev/ttySOMETHING" without the quotes - you probably want to copy paste it)? ' -r
        ttyport=$REPLY
        echo -n "Ok, "
        if [[ -z "$ttyport" ]]; then
            echo -n Carelink
        else
            echo -n TTY $ttyport
        fi
        echo " it is. "
    fi


    if [[ ! -z "${ttyport}" ]]; then
      echo "Medtronic pumps come in two types: WW (Worldwide) pumps, and NA (North America) pumps."
      echo "Confusingly, North America pumps may also be used outside of North America."
      echo ""
      echo "USA pumps have a serial number / model number that has 'NA' in it."
      echo "Non-USA pumps have a serial number / model number that 'WW' in it."
      echo ""
      echo "When using MMeowlink, we need to know which frequency we should use:"
      read -p "Are you using a USA/North American pump? If so, just hit enter. Otherwise enter WW: " -r
      radio_locale=$REPLY
      echo -n "Ok, "
      # Force uppercase, just in case the user entered ww
      radio_locale=${radio_locale^^}

      # check if user has a TI USB stick and a WorldWide pump and want's to reset the USB subsystem during mmtune if the TI USB fails
      ww_ti_usb_reset="no" # assume you don't want it by default
      if [[ $radio_locale =~ ^WW$ ]]; then
        echo "If you have a TI USB stick and a WW pump and a Raspberry PI, you might want to reset the USB subsystem if it can't be found during a mmtune process"
        read -p "Do you want to reset the USB system in case the TI USB stick can't be found during a mmtune proces? Use y if so. Otherwise just hit enter (default no): " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
          ww_ti_usb_reset="yes"
        else
          ww_ti_usb_reset="no" 
        fi
      fi

      if [[ -z "${radio_locale}" ]]; then
          radio_locale='US'
      fi

      echo "-n ${radio_locale} it is"
    fi

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
    if [[ ! -z $BT_MAC ]]; then
       read -p "For BT Tethering enter phone Bluetooth MAC address (i.e. AA:BB:CC:DD:EE:FF) hit enter to skip " -r
       BT_MAC=$REPLY
       echo "Ok, $BT_MAC it is."
       if [[ -z $BT_MAC ]]; then
          echo Ok, no Bluetooth for you.
          else
          echo "Ok, $BT_MAC it is."
       fi
    fi
    if [[ ! -z $BT_PEB ]]; then
       read -p "For Pancreabble enter Pebble mac id (i.e. AA:BB:CC:DD:EE:FF) hit enter to skip " -r
       BT_PEB=$REPLY
       echo "Ok, $BT_PEB it is."
    fi
    read -p "Do you need any advanced features? y/[N] " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enable automatic sensitivity adjustment? y/[N] " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ENABLE+=" autosens "
        fi
        read -p "Enable autotuning of basals and ratios? y/[N] " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ENABLE+=" autotune "
        fi
        read -p "Enable advanced meal assist? y/[N] " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ENABLE+=" meal "
        fi
    fi
else 
   if [[ $ww_ti_usb_reset =~ ^[Yy] ]]; then
      ww_ti_usb_reset="yes"
   else
      ww_ti_usb_reset="no"
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
if [[ "$max_iob" != "0" ]]; then echo -n ", max_iob $max_iob"; fi
if [[ ! -z "$max_daily_safety_multiplier" ]]; then
    echo -n ", max_daily_safety_multiplier $max_daily_safety_multiplier";
fi
if [[ ! -z "$current_basal_safety_multiplier" ]]; then
    echo -n ", current_basal_safety_multiplier $current_basal_safety_multiplier";
fi
if [[ ! -z "$bolussnooze_dia_divisor" ]]; then
    echo -n ", bolussnooze_dia_divisor $bolussnooze_dia_divisor";
fi
if [[ ! -z "$min_5m_carbimpact" ]]; then
    echo -n ", min_5m_carbimpact $min_5m_carbimpact";
fi
if [[ ! -z "$ENABLE" ]]; then echo -n ", advanced features $ENABLE"; fi
echo

# This section is echoing (commenting) back the options you gave it during the interactive setup script.
# The "| tee -a /tmp/oref0-runagain.sh" part is also appending it to a file so you can run it again more easily in the future.

# create temporary file for oref0-runagain.sh
OREF0_RUNAGAIN=`mktemp /tmp/oref0-runagain.XXXXXXXXXX`
echo "#!/bin/bash" > $OREF0_RUNAGAIN
echo "# To run again with these same options, use:" | tee $OREF0_RUNAGAIN
echo -n "oref0-setup --dir=$directory --serial=$serial --cgm=$CGM" | tee -a $OREF0_RUNAGAIN
if [[ ${CGM,,} =~ "shareble" ]]; then
    echo -n " --bleserial=$BLE_SERIAL" | tee -a $OREF0_RUNAGAIN
fi
echo -n " --ns-host=$NIGHTSCOUT_HOST --api-secret=$API_SECRET" | tee -a $OREF0_RUNAGAIN
if [[ ! -z "$ttyport" ]]; then
    echo -n " --tty=$ttyport" | tee -a $OREF0_RUNAGAIN
fi
if [[ "$max_iob" -ne 0 ]]; then echo -n " --max_iob=$max_iob" | tee -a $OREF0_RUNAGAIN; fi
if [[ ! -z "$max_daily_safety_multiplier" ]]; then
    echo -n " --max_daily_safety_multiplier=$max_daily_safety_multiplier" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$current_basal_safety_multiplier" ]]; then
    echo -n " --current_basal_safety_multiplier=$current_basal_safety_multiplier" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$bolussnooze_dia_divisor" ]]; then
    echo -n " --bolussnooze_dia_divisor=$bolussnooze_dia_divisor" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$min_5m_carbimpact" ]]; then
    echo -n " --min_5m_carbimpact=$min_5m_carbimpact" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$ENABLE" ]]; then echo -n " --enable='$ENABLE'" | tee -a $OREF0_RUNAGAIN; fi
if [[ ! -z "$radio_locale" ]]; then echo -n " --radio_locale='$radio_locale'" | tee -a $OREF0_RUNAGAIN; fi
if [[ $ww_ti_usb_reset =~ ^[Yy]$ ]]; then echo -n " --ww_ti_usb_reset='$ww_ti_usb_reset'" | tee -a $OREF0_RUNAGAIN; fi
if [[ ! -z "$BLE_MAC" ]]; then echo -n " --blemac='$BLE_MAC'" | tee -a $OREF0_RUNAGAIN; fi
if [[ ! -z "$BT_MAC" ]]; then echo -n " --btmac='$BT_MAC'" | tee -a $OREF0_RUNAGAIN; fi
if [[ ! -z "$BT_PEB" ]]; then echo -n " --btpeb='$BT_PEB'" | tee -a $OREF0_RUNAGAIN; fi
echo; echo | tee -a $OREF0_RUNAGAIN
chmod 755 $OREF0_RUNAGAIN

read -p "Continue? y/[N] " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then

echo -n "Checking $directory: "
mkdir -p $directory
if ( cd $directory && git status 2>/dev/null >/dev/null && openaps use -h >/dev/null ); then
    echo $directory already exists
elif openaps init $directory; then
    echo $directory initialized
else
    die "Can't init $directory"
fi
cd $directory || die "Can't cd $directory"

# Taking the oref0-runagain.sh from tmp to $directory
mv $OREF0_RUNAGAIN ./oref0-runagain.sh

mkdir -p monitor || die "Can't mkdir monitor"
mkdir -p raw-cgm || die "Can't mkdir raw-cgm"
mkdir -p cgm || die "Can't mkdir cgm"
mkdir -p settings || die "Can't mkdir settings"
mkdir -p enact || die "Can't mkdir enact"
mkdir -p upload || die "Can't mkdir upload"
if [[ ${CGM,,} =~ "xdrip" ]]; then
	mkdir -p xdrip || die "Can't mkdir xdrip"
fi

mkdir -p $HOME/src/
if [ -d "$HOME/src/oref0/" ]; then
    echo "$HOME/src/oref0/ already exists; pulling latest"
    (cd $HOME/src/oref0 && git fetch && git pull) || die "Couldn't pull latest oref0"
else
    echo -n "Cloning oref0: "
    (cd $HOME/src && git clone git://github.com/openaps/oref0.git) || die "Couldn't clone oref0"
fi
echo Checking oref0 installation
if git branch | grep "* master"; then
    npm list -g oref0 | egrep oref0@0.4.[2-9] || (echo Installing latest oref0 package && sudo npm install -g oref0)
else
    npm list -g oref0 | egrep oref0@0.5.[0-9] || (echo Installing latest oref0 from $HOME/src/oref0/ && cd $HOME/src/oref0/ && npm run global-install)
fi

echo Checking mmeowlink installation
#if openaps vendor add --path . mmeowlink.vendors.mmeowlink 2>&1 | grep "No module"; then
pip show mmeowlink | egrep "Version: 0.11." || (
    echo Installing latest mmeowlink
    sudo pip install -U mmeowlink || die "Couldn't install mmeowlink"
)
#fi

cd $directory || die "Can't cd $directory"
if [[ "$max_iob" -eq 0 && -z "$max_daily_safety_multiplier" && -z "&current_basal_safety_multiplier" && -z "$bolussnooze_dia_divisor" && -z "$min_5m_carbimpact" ]]; then
    oref0-get-profile --exportDefaults > preferences.json || die "Could not run oref0-get-profile"
else
    preferences_from_args=()
    if [[ $max_iob -ne 0 ]]; then
	preferences_from_args+="\"max_iob\":$max_iob "
    fi
    if [[ ! -z "$max_daily_safety_multiplier" ]]; then
        preferences_from_args+="\"max_daily_safety_multiplier\":$max_daily_safety_multiplier "
    fi
    if [[ ! -z "$current_basal_safety_multiplier" ]]; then
        preferences_from_args+="\"current_basal_safety_multiplier\":$current_basal_safety_multiplier "
    fi
    if [[ ! -z "$bolussnooze_dia_divisor" ]]; then
        preferences_from_args+="\"bolussnooze_dia_divisor\":$bolussnooze_dia_divisor "
    fi
    if [[ ! -z "$min_5m_carbimpact" ]]; then
        preferences_from_args+="\"min_5m_carbimpact\":$min_5m_carbimpact "
    fi
    function join_by { local IFS="$1"; shift; echo "$*"; }
    echo "{ $(join_by , ${preferences_from_args[@]}) }" > preferences_from_args.json
    oref0-get-profile --updatePreferences preferences_from_args.json > preferences.json && rm preferences_from_args.json || die "Could not run oref0-get-profile"
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
    ( killall -g openaps; killall -g oref0-pump-loop) 2>/dev/null; openaps device remove ns 2>/dev/null
    echo "Running nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET"
    nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET || die "Could not run nightscout autoconfigure-device-crud"
fi

# import template
for type in vendor device report alias; do
    echo importing $type file
    cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
done
echo Checking for BT Mac, BT Peb or Shareble
if [[ ! -z "$BT_PEB" || ! -z "$BT_MAC" || ${CGM,,} =~ "shareble" ]]; then
    # Install Bluez for BT Tethering
    echo Checking bluez installation
    if ! bluetoothd --version | grep -q 5.44 2>/dev/null; then
        cd $HOME/src/ && wget https://www.kernel.org/pub/linux/bluetooth/bluez-5.44.tar.gz && tar xvfz bluez-5.44.tar.gz || die "Couldn't download bluez"
        cd $HOME/src/bluez-5.44 && ./configure --enable-experimental --disable-systemd && \
        make && sudo make install && sudo cp ./src/bluetoothd /usr/local/bin/ || die "Couldn't make bluez"
        oref0-bluetoothup
    else
        echo bluez v 5.44 already installed
    fi
fi
# add/configure devices
if [[ ${CGM,,} =~ "g5" ]]; then
    openaps use cgm config --G5
    openaps report add raw-cgm/raw-entries.json JSON cgm oref0_glucose --hours "24.0" --threshold "100" --no-raw
elif [[ ${CGM,,} =~ "shareble" ]]; then
    echo Checking Adafruit_BluefruitLE installation
    if ! python -c "import Adafruit_BluefruitLE" 2>/dev/null; then
        if [ -d "$HOME/src/Adafruit_Python_BluefruitLE/" ]; then
            echo "$HOME/src/Adafruit_Python_BluefruitLE/ already exists; pulling latest master branch"
            (cd $HOME/src/Adafruit_Python_BluefruitLE && git fetch && git checkout wip/bewest/custom-gatt-profile && git pull) || die "Couldn't pull latest Adafruit_Python_BluefruitLE wip/bewest/custom-gatt-profile"
        else
            echo -n "Cloning Adafruit_Python_BluefruitLE wip/bewest/custom-gatt-profile: "
            # TODO: get this moved over to openaps and install with pip
            (cd $HOME/src && git clone -b wip/bewest/custom-gatt-profile https://github.com/bewest/Adafruit_Python_BluefruitLE.git) || die "Couldn't clone Adafruit_Python_BluefruitLE wip/bewest/custom-gatt-profile"
        fi
        echo Installing Adafruit_BluefruitLE && cd $HOME/src/Adafruit_Python_BluefruitLE && sudo python setup.py develop || die "Couldn't install Adafruit_BluefruitLE"
    fi
    echo Checking openxshareble installation
    if ! python -c "import openxshareble" 2>/dev/null; then
        echo Installing openxshareble && sudo pip install git+https://github.com/openaps/openxshareble.git@dev || die "Couldn't install openxshareble"
    fi
    sudo apt-get -y install bc jq libusb-dev libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev python-dbus || die "Couldn't apt-get install: run 'sudo apt-get update' and try again?"
    echo Checking bluez installation
    if  bluetoothd --version | grep -q 5.44 2>/dev/null; then
        sudo cp $HOME/src/openxshareble/bluetoothd.conf /etc/dbus-1/system.d/bluetooth.conf || die "Couldn't copy bluetoothd.conf"
    fi
     # add two lines to /etc/rc.local if they are missing.
    if ! grep -q '/usr/local/bin/bluetoothd --experimental &' /etc/rc.local; then
        sed -i"" 's/^exit 0/\/usr\/local\/bin\/bluetoothd --experimental \&\n\nexit 0/' /etc/rc.local
    fi
    if ! grep -q 'bluetooth_rfkill_event >/dev/null 2>&1 &' /etc/rc.local; then
        sed -i"" 's/^exit 0/bluetooth_rfkill_event >\/dev\/null 2>\&1 \&\n\nexit 0/' /etc/rc.local
    fi
    # comment out existing line if it exists and isn't already commented out
    sed -i"" 's/^screen -S "brcm_patchram_plus" -d -m \/usr\/local\/sbin\/bluetooth_patchram.sh/# &/' /etc/rc.local
fi
if [[ ${CGM,,} =~ "shareble" || ${CGM,,} =~ "g4-local" ]]; then
    mkdir -p $directory-cgm-loop
    if ( cd $directory-cgm-loop && git status 2>/dev/null >/dev/null && openaps use -h >/dev/null ); then
        echo $directory-cgm-loop already exists
    elif openaps init $directory-cgm-loop; then
        echo $directory-cgm-loop initialized
    else
        die "Can't init $directory-cgm-loop"
    fi
    cd $directory-cgm-loop || die "Can't cd $directory-cgm-loop"
    mkdir -p monitor || die "Can't mkdir monitor"
    mkdir -p nightscout || die "Can't mkdir nightscout"

    openaps device remove cgm 2>/dev/null

    # configure ns
    if [[ ! -z "$NIGHTSCOUT_HOST" && ! -z "$API_SECRET" ]]; then
        echo "Removing any existing ns device: "
        ( killall -g openaps; killall -g oref0-pump-loop) 2>/dev/null; openaps device remove ns 2>/dev/null
        echo "Running nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET"
        nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET || die "Could not run nightscout autoconfigure-device-crud"
    fi

    if [[ ${CGM,,} =~ "g4-local" ]]; then
        sudo apt-get -y install bc
        openaps device add cgm dexcom || die "Can't add CGM"
        for type in cgm-loop; do
            echo importing $type file
            cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
        done
    elif [[ ${CGM,,} =~ "shareble" ]]; then
        # import shareble stuff
        for type in shareble cgm-loop; do
            echo importing $type file
            cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
        done

        if [[ -z "$BLE_MAC" ]]; then
            read -p "Please go into your Dexcom's Share settings, forget any existing device, turn Share back on, and press Enter."
            openaps use cgm list_dexcom
            read -p "What is your G4 Share MAC address? (i.e. FE:DC:BA:98:78:54) " -r
            BLE_MAC=$REPLY
            echo "$BLE_MAC? Got it."
        fi
        echo openaps use cgm configure --serial $BLE_SERIAL --mac $BLE_MAC
        openaps use cgm configure --serial $BLE_SERIAL --mac $BLE_MAC || die "Couldn't configure Share serial and MAC"
    fi

    cd $directory || die "Can't cd $directory"
fi
grep -q pump.ini .gitignore 2>/dev/null || echo pump.ini >> .gitignore
git add .gitignore

if [[ "$ttyport" =~ "spi" ]]; then
    echo Checking kernel for spi_serial installation
    if ! python -c "import spi_serial" 2>/dev/null; then
        if uname -r 2>&1 | egrep "^4.1[0-9]"; then # kernel >= 4.10+, use pietergit version of spi_serial (does not use mraa)
           echo Installing spi_serial && sudo pip install --upgrade git+https://github.com/pietergit/spi_serial.git || die "Couldn't install pietergit/spi_serial"
        else # kernel < 4.10, use scottleibrand version of spi_serial (requires mraa)
           echo Installing spi_serial && sudo pip install --upgrade git+https://github.com/scottleibrand/spi_serial.git || die "Couldn't install scottleibrand/spi_serial"           
        fi
        #echo Installing spi_serial && sudo pip install --upgrade git+https://github.com/EnhancedRadioDevices/spi_serial || die "Couldn't install spi_serial"
    fi

    echo Checking kernel for mraa installation
    if uname -r 2>&1 | egrep "^4.1[0-9]"; then # don't install mraa on 4.10+ kernels
       echo "Skipping mraa install for kernel 4.10+"
    else # check if mraa is installed
      if ! ldconfig -p | grep -q mraa; then # if not installed, install it
          echo Installing swig etc.
          sudo apt-get install -y libpcre3-dev git cmake python-dev swig || die "Could not install swig etc."
          if [ -d "$HOME/src/mraa/" ]; then
              echo "$HOME/src/mraa/ already exists; pulling latest master branch"
              (cd $HOME/src/mraa && git fetch && git checkout master && git pull) || die "Couldn't pull latest mraa master"
          else
              echo -n "Cloning mraa master: "
              (cd $HOME/src && git clone -b master https://github.com/intel-iot-devkit/mraa.git) || die "Couldn't clone mraa master"
          fi
          ( cd $HOME/src/ && mkdir -p mraa/build && cd $_ && cmake .. -DBUILDSWIGNODE=OFF && \
          make && sudo make install && echo && touch /tmp/reboot-required && echo mraa installed. Please reboot before using. && echo ) || die "Could not compile mraa"
          sudo bash -c "grep -q i386-linux-gnu /etc/ld.so.conf || echo /usr/local/lib/i386-linux-gnu/ >> /etc/ld.so.conf && ldconfig" || die "Could not update /etc/ld.so.conf"
      fi
    fi 

fi

echo Checking openaps dev installation
if ! openaps --version 2>&1 | egrep "0.[2-9].[0-9]"; then
    # TODO: switch this back to master once https://github.com/openaps/openaps/pull/116 is merged/released
    echo Installing latest openaps dev && sudo pip install git+https://github.com/openaps/openaps.git@dev || die "Couldn't install openaps"
fi

cd $directory || die "Can't cd $directory"
echo "Removing any existing pump device:"
( killall -g openaps; killall -g oref0-pump-loop) 2>/dev/null; openaps device remove pump 2>/dev/null
if [[ -z "$ttyport" ]]; then
    openaps device add pump medtronic $serial || die "Can't add pump"
    # carelinks can't listen for silence or mmtune, so just do a preflight check instead
    openaps alias add wait-for-silence 'report invoke monitor/temp_basal.json'
    openaps alias add wait-for-long-silence 'report invoke monitor/temp_basal.json'
    openaps alias add mmtune 'report invoke monitor/temp_basal.json'
else
    # radio_locale requires openaps 0.2.0-dev or later
    openaps device add pump mmeowlink subg_rfspy $ttyport $serial $radio_locale || die "Can't add pump"
    openaps alias add wait-for-silence '! bash -c "(mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 1 | grep -q comms && echo -n Radio ok, || openaps mmtune) && echo -n \" Listening: \"; for i in $(seq 1 100); do echo -n .; mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 30 2>/dev/null | egrep -v subg | egrep No && break; done"'
    openaps alias add wait-for-long-silence '! bash -c "echo -n \"Listening: \"; for i in $(seq 1 200); do echo -n .; mmeowlink-any-pump-comms.py --port '$ttyport' --wait-for 45 2>/dev/null | egrep -v subg | egrep No && break; done"'
    if [[ ${radio_locale,,} =~ "ww" ]]; then
      if [ -d "$HOME/src/subg_rfspy/" ]; then
        echo "$HOME/src/subg_rfspy/ already exists; pulling latest"
        (cd $HOME/src/subg_rfspy && git fetch && git pull) || die "Couldn't pull latest subg_rfspy"
      else
        echo -n "Cloning subg_rfspy: "
        (cd $HOME/src && git clone https://github.com/ps2/subg_rfspy) || die "Couldn't clone oref0"
      fi

      # from 0.5.0 the subg-ww-radio-parameters script will be run from oref0_init_pump_comms.py
      # this will be called when mmtune is use with a WW pump. 
      # See https://github.com/oskarpearson/mmeowlink/issues/51 or https://github.com/oskarpearson/mmeowlink/wiki/Non-USA-pump-settings for details
      # use --ww_ti_usb_reset=yes if using a TI USB stick and a WW pump. This will reset the USB subsystem if the TI USB device is not foundTI USB (instead of calling reset.py)

      # Hack to check if radio_locale has been set in pump.ini. This is a temporary workaround for https://github.com/oskarpearson/mmeowlink/issues/55
      # It will remove empty line at the end of pump.ini and then append radio_locale if it's not there yet
      # TODO: remove once https://github.com/openaps/openaps/pull/112 has been released in a openaps version
      grep -q radio_locale pump.ini ||  echo "$(< pump.ini)" > pump.ini ; echo "radio_locale=$radio_locale" >> pump.ini
    fi
fi

# Medtronic CGM
if [[ ${CGM,,} =~ "mdt" ]]; then
    sudo pip install -U openapscontrib.glucosetools || die "Couldn't install glucosetools"
    openaps device remove cgm 2>/dev/null
    if [[ -z "$ttyport" ]]; then
        openaps device add cgm medtronic $serial || die "Can't add cgm"
    else
        openaps device add cgm mmeowlink subg_rfspy $ttyport $serial $radio_locale || die "Can't add cgm"
    fi
    for type in mdt-cgm; do
        echo importing $type file
        cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
    done
fi

# xdrip CGM (xDripAPS)
if [[ ${CGM,,} =~ "xdrip" ]]; then
    echo xdrip selected as CGM, so configuring xDripAPS
    sudo apt-get install sqlite3 || die "Can't add xdrip cgm - error installing sqlite3"
    sudo pip install flask || die "Can't add xdrip cgm - error installing flask"
    sudo pip install flask-restful || die "Can't add xdrip cgm - error installing flask-restful"
    git clone https://github.com/colinlennon/xDripAPS.git $HOME/.xDripAPS
    mkdir -p $HOME/.xDripAPS_data
    for type in xdrip-cgm; do
        echo importing $type file
        cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
    done
    touch /tmp/reboot-required
fi

# Install EdisonVoltage
if egrep -i "edison" /etc/passwd 2>/dev/null; then
   echo "Checking if EdisonVoltage is already installed"
   if [ -d "$HOME/src/EdisonVoltage/" ]; then
      echo "EdisonVoltage already installed"
   else
      echo "Installing EdisonVoltage"
      cd $HOME/src && git clone -b master git://github.com/cjo20/EdisonVoltage.git || (cd EdisonVoltage && git checkout master && git pull)
      cd $HOME/src/EdisonVoltage
      make voltage
   fi
   cd $directory || die "Can't cd $directory"
   for type in edisonbattery; do
     echo importing $type file
     cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
  done
fi
# Install Pancreabble
echo Checking for BT Pebble Mac 
if [[ ! -z "$BT_PEB" ]]; then
   sudo apt-get -y install jq
   sudo pip install libpebble2
   sudo pip install --user git+git://github.com/mddub/pancreabble.git
   oref0-bluetoothup
   sudo rfcomm bind hci0 $BT_PEB
   for type in pancreabble; do
     echo importing $type file
     cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
  done 
  sudo cp $HOME/src/oref0/lib/oref0-setup/pancreoptions.json $directory/pancreoptions.json 
fi  
# configure optional features passed to enact/suggested.json report
if [[ $ENABLE =~ autosens && $ENABLE =~ meal ]]; then
    EXTRAS="settings/autosens.json monitor/meal.json"
elif [[ $ENABLE =~ autosens ]]; then
    EXTRAS="settings/autosens.json"
elif [[ $ENABLE =~ meal ]]; then
    EXTRAS='"" monitor/meal.json'
fi
echo Running: openaps report add enact/suggested.json text determine-basal shell monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json $EXTRAS
openaps report add enact/suggested.json text determine-basal shell monitor/iob.json monitor/temp_basal.json monitor/glucose.json settings/profile.json $EXTRAS

# configure autotune if enabled
if [[ $ENABLE =~ autotune ]]; then
    sudo apt-get -y install jq
    cd $directory || die "Can't cd $directory"
    for type in autotune; do
      echo importing $type file
      cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
    done
fi

# configure supermicrobolus if enabled
# WARNING: supermicrobolus mode is not yet documented or ready for general testing
# It should only be tested with a disconnected pump not administering insulin.
# If you aren't sure what you're doing, *DO NOT* enable this.
# If you ignore this warning, it *WILL* administer extra post-meal insulin, which may cause low blood sugar.
if [[ $ENABLE =~ microbolus ]]; then
    sudo apt-get -y install bc
    cd $directory || die "Can't cd $directory"
    for type in supermicrobolus; do
      echo importing $type file
      cat $HOME/src/oref0/lib/oref0-setup/$type.json | openaps import || die "Could not import $type.json"
    done
fi

# Create ~/.profile so that openaps commands can be executed from the command line
# as long as we still use enivorement variables it's easy that the openaps commands work from both crontab and from a common shell
# TODO: remove API_SECRET and NIGHTSCOUT_HOST (see https://github.com/openaps/oref0/issues/299)
echo Add NIGHTSCOUT_HOST and API_SECRET to $HOME/.profile
(cat $HOME/.profile | grep -q "NIGHTSCOUT_HOST" || echo export NIGHTSCOUT_HOST="$NIGHTSCOUT_HOST") >> $HOME/.profile
(cat $HOME/.profile | grep -q "API_SECRET" || echo export API_SECRET="`nightscout hash-api-secret $API_SECRET`") >> $HOME/.profile

echo "Adding OpenAPS log shortcuts"
oref0-log-shortcuts

echo
if [[ "$ttyport" =~ "spi" ]]; then
    echo Resetting spi_serial
    reset_spi_serial.py
fi
echo Attempting to communicate with pump:
( killall -g openaps; killall -g oref0-pump-loop)
openaps mmtune
echo

read -p "Schedule openaps in cron? y/[N] " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then

    echo Saving existing crontab to $HOME/crontab.txt:
    crontab -l | tee $HOME/crontab.old.txt
    read -p "Would you like to remove your existing crontab first? y/[N] " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        crontab -r
    fi

# add crontab entries
    (crontab -l; crontab -l | grep -q "$NIGHTSCOUT_HOST" || echo NIGHTSCOUT_HOST=$NIGHTSCOUT_HOST) | crontab -
    (crontab -l; crontab -l | grep -q "API_SECRET=" || echo API_SECRET=$(nightscout hash-api-secret $API_SECRET)) | crontab -
    (crontab -l; crontab -l | grep -q "PATH=" || echo "PATH=$PATH" ) | crontab -
    (crontab -l; crontab -l | grep -q "oref0-online $BT_MAC" || echo '* * * * * ps aux | grep -v grep | grep -q "oref0-online '$BT_MAC'" || oref0-online '$BT_MAC' >> /var/log/openaps/network.log' ) | crontab -
    (crontab -l; crontab -l | grep -q "sudo wpa_cli scan" || echo '* * * * * sudo wpa_cli scan') | crontab -
    (crontab -l; crontab -l | grep -q "killall -g --older-than 15m oref0" || echo '* * * * * ( killall -g --older-than 15m openaps; killall -g --older-than 15m oref0-pump-loop; killall -g --older-than 15m openaps-report )') | crontab -
    # repair or reset git repository if it's corrupted or disk is full
    (crontab -l; crontab -l | grep -q "cd $directory && oref0-reset-git" || echo "* * * * * cd $directory && oref0-reset-git") | crontab -
    # truncate git history to 1000 commits if it has grown past 1500
    (crontab -l; crontab -l | grep -q "oref0-truncate-git-history" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q oref0-truncate-git-history || oref0-truncate-git-history") | crontab -
    if [[ ${CGM,,} =~ "shareble" || ${CGM,,} =~ "g4-upload" ]]; then
        # repair or reset cgm-loop git repository if it's corrupted or disk is full
        (crontab -l; crontab -l | grep -q "cd $directory-cgm-loop && oref0-reset-git" || echo "* * * * * cd $directory-cgm-loop && oref0-reset-git") | crontab -
        # truncate cgm-loop git history to 1000 commits if it has grown past 1500
        (crontab -l; crontab -l | grep -q "cd $directory-cgm-loop && oref0-truncate-git-history" || echo "* * * * * cd $directory-cgm-loop && oref0-truncate-git-history") | crontab -
        (crontab -l; crontab -l | grep -q "cd $directory-cgm-loop && ps aux | grep -v grep | grep -q 'openaps monitor-cgm'" || echo "* * * * * cd $directory-cgm-loop && ps aux | grep -v grep | grep -q 'openaps monitor-cgm' || ( date; openaps monitor-cgm) | tee -a /var/log/openaps/cgm-loop.log; cp -up monitor/glucose-raw-merge.json $directory/cgm/glucose.json ; cp -up $directory/cgm/glucose.json $directory/monitor/glucose.json") | crontab -
    elif [[ ${CGM,,} =~ "xdrip" ]]; then
        (crontab -l; crontab -l | grep -q "cd $directory && ps aux | grep -v grep | grep -q 'openaps monitor-xdrip'" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps monitor-xdrip' || ( date; openaps monitor-xdrip) | tee -a /var/log/openaps/xdrip-loop.log; cp -up $directory/xdrip/glucose.json $directory/monitor/glucose.json") | crontab -
        (crontab -l; crontab -l | grep -q "xDripAPS.py" || echo "@reboot python $HOME/.xDripAPS/xDripAPS.py") | crontab -
    elif [[ $ENABLE =~ dexusb ]]; then
        (crontab -l; crontab -l | grep -q "@reboot .*dexusb-cgm" || echo "@reboot cd $directory && /usr/bin/python -u /usr/local/bin/oref0-dexusb-cgm-loop >> /var/log/openaps/cgm-dexusb-loop.log 2>&1" ) | crontab -
    elif ! [[ ${CGM,,} =~ "mdt" ]]; then # use nightscout for cgm
        (crontab -l; crontab -l | grep -q "cd $directory && ps aux | grep -v grep | grep -q 'openaps get-bg'" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps get-bg' || ( date; openaps get-bg ; cat cgm/glucose.json | json -a sgv dateString | head -1 ) | tee -a /var/log/openaps/cgm-loop.log") | crontab -
    fi
    (crontab -l; crontab -l | grep -q "cd $directory && ps aux | grep -v grep | grep -q 'openaps ns-loop'" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps ns-loop' || openaps ns-loop | tee -a /var/log/openaps/ns-loop.log") | crontab -
    if [[ $ENABLE =~ autosens ]]; then
        (crontab -l; crontab -l | grep -q "cd $directory && ps aux | grep -v grep | grep -q 'openaps autosens' || openaps autosens 2>&1" || echo "* * * * * cd $directory && ps aux | grep -v grep | grep -q 'openaps autosens' || openaps autosens 2>&1 | tee -a /var/log/openaps/autosens-loop.log") | crontab -
    fi
    if [[ $ENABLE =~ autotune ]]; then
        # autotune nightly at 12:05am using data from NS
        (crontab -l; crontab -l | grep -q "oref0-autotune -d=$directory -n=$NIGHTSCOUT_HOST" || echo "5 0 * * * ( oref0-autotune -d=$directory -n=$NIGHTSCOUT_HOST && cat $directory/autotune/profile.json | json | grep -q start && cp $directory/autotune/profile.json $directory/settings/autotune.json) 2>&1 | tee -a /var/log/openaps/autotune.log") | crontab -
    fi
    if [[ "$ttyport" =~ "spi" ]]; then
        (crontab -l; crontab -l | grep -q "reset_spi_serial.py" || echo "@reboot reset_spi_serial.py") | crontab -
        (crontab -l; crontab -l | grep -q "oref0-radio-reboot" || echo "* * * * * oref0-radio-reboot") | crontab -
    fi
    if [[ $ENABLE =~ microbolus ]]; then
        (crontab -l; crontab -l | grep -q "cd $directory && ( ps aux | grep -v grep | grep -q 'bin/oref0-pump-loop'" || echo "* * * * * cd $directory && ( ps aux | grep -v grep | grep -q 'bin/oref0-pump-loop' || oref0-pump-loop --microbolus ) 2>&1 | tee -a /var/log/openaps/pump-loop.log") | crontab -
    else
        (crontab -l; crontab -l | grep -q "cd $directory && ( ps aux | grep -v grep | grep -q 'openaps pump-loop'" || echo "* * * * * cd $directory && ( ps aux | grep -v grep | grep -q 'openaps pump-loop' || openaps pump-loop ) 2>&1 | tee -a /var/log/openaps/pump-loop.log") | crontab -
    fi
    if [[ ! -z "$BT_PEB" ]]; then
       (crontab -l; crontab -l | grep -q "cd $directory && ( ps aux | grep -v grep | grep -q 'peb-urchin-status $BT_PEB '" || echo "* * * * * cd $directory && ( ps aux | grep -v grep | grep -q 'peb-urchin-status $BT_PEB' || peb-urchin-status $BT_PEB ) 2>&1 | tee -a /var/log/openaps/urchin-loop.log") | crontab -
    fi
    if [[ ! -z "$BT_PEB" || ! -z "$BT_MAC" ]]; then
       (crontab -l; crontab -l | grep -q "oref0-bluetoothup" || echo '* * * * * ps aux | grep -v grep | grep -q "oref0-bluetoothup" || oref0-bluetoothup >> /var/log/openaps/network.log' ) | crontab -
    fi
    # proper shutdown once the EdisonVoltage very low (< 3050mV; 2950 is dead)
    if egrep -i "edison" /etc/passwd 2>/dev/null; then
     (crontab -l; crontab -l | grep -q "cd $directory && openaps battery-status" || echo "*/15 * * * * cd $directory && openaps battery-status; cat $directory/monitor/edison-battery.json | json batteryVoltage | awk '{if (\$1<=3050)system(\"sudo shutdown -h now\")}'") | crontab -
    fi
    (crontab -l; crontab -l | grep -q "cd $directory && oref0-delete-future-entries" || echo "@reboot cd $directory && oref0-delete-future-entries") | crontab -

    crontab -l | tee $HOME/crontab.txt
fi

if [[ ${CGM,,} =~ "shareble" ]]; then
    echo
    echo "To pair your G4 Share receiver, open its Setttings, select Share, Forget Device (if previously paired), then turn sharing On"
fi


fi # from 'read -p "Continue? y/[N] " -r' after interactive setup is complete

if [ -e /tmp/reboot-required ]; then
  read -p "Reboot required.  Press enter to reboot or Ctrl-C to cancel"
  sudo reboot
fi
