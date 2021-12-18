#!/usr/bin/env bash

# This script sets up an openaps environment by defining the required devices,
# reports, and aliases, and optionally enabling it in cron,
# plus editing other user-entered configuration settings.
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

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0-setup.sh in the right directory?"; exit 1)

usage "$@" <<EOT
Usage: $self <--dir=directory> <--serial=pump_serial_#> [--tty=/dev/ttySOMETHING] [--max_iob=0] [--ns-host=https://mynightscout.herokuapp.com] [--api-secret=[myplaintextapisecret|token=subjectname-plaintexthashsecret] [--cgm=(G4-go|G5|MDT|xdrip|xdrip-js)] [--bleserial=SM123456] [--blemac=FE:DC:BA:98:76:54] [--dexcom_tx_sn=12A34B] [--btmac=AB:CD:EF:01:23:45] [--enable='autotune'] [--radio_locale=(WW|US)]
EOT

# defaults
max_iob=0 # max_IOB will default to zero if not set in setup script
CGM="G4-go"
DIR=""
directory=""
EXTRAS=""
radio_locale="US"
radiotags="cc111x"
ecc1medtronicversion="latest"
ecc1dexcomversion="latest"
hardwaretype=explorer-board

# Echo text, but in bright-blue. Used for confirmation echo text. This takes
# the same arguments as echo, including the -n option.
function echocolor() {
    echo -e -n "\e[1;34m"
    echo "$@"
    echo -e -n "\e[0m"
}


for i in "$@"; do
case $i in
    -d=*|--dir=*)
    DIR="${i#*=}"
    # ~/ paths have to be expanded manually
    DIR="${DIR/#\~/$HOME}"
    directory="$(readlink -m $DIR)"
    ;;
    -s=*|--serial=*)
    serial="${i#*=}"
    ;;
    -rl=*|--radio_locale=*)
    radio_locale="${i#*=}"
    ;;
    -t=*|--tty=*)
    ttyport="${i#*=}"
    ;;
    -m=*|--max_iob=*)
    max_iob="${i#*=}"
    ;;
    -mdsm=*|--max_daily_safety_multiplier=*)
    max_daily_safety_multiplier="${i#*=}"
    ;;
    -cbsm=*|--current_basal_safety_multiplier=*)
    current_basal_safety_multiplier="${i#*=}"
    ;;
    #-bdd=*|--bolussnooze_dia_divisor=*)
    #bolussnooze_dia_divisor="${i#*=}"
    #;;
    -m5c=*|--min_5m_carbimpact=*)
    min_5m_carbimpact="${i#*=}"
    ;;
    -c=*|--cgm=*)
    CGM="${i#*=}"
    ;;
    -n=*|--ns-host=*)
    NIGHTSCOUT_HOST=$(echo ${i#*=} | sed 's/\/$//g')
    ;;
    -a=*|--api-secret=*)
    API_SECRET="${i#*=}"
    ;;
    -e=*|--enable=*)
    ENABLE="${i#*=}"
    ;;
    -b=*|--bleserial=*)
    BLE_SERIAL="${i#*=}"
    ;;
    -l=*|--blemac=*)
    BLE_MAC="${i#*=}"
    ;;
    -dtx=*|--dexcom_tx_sn=*)
    DEXCOM_CGM_TX_ID="${i#*=}"
    ;;
    --btmac=*)
    BT_MAC="${i#*=}"
    ;;
    -p=*|--btpeb=*)
    BT_PEB="${i#*=}"
    ;;
    -pt=*|--pushover_token=*)
    PUSHOVER_TOKEN="${i#*=}"
    ;;
    -pu=*|--pushover_user=*)
    PUSHOVER_USER="${i#*=}"
    ;;
    -ht=*|--hardwaretype=*)
    hardwaretype="${i#*=}"
    ;;
    -rt=*|--radiotags=*)
    radiotags="${i#*=}"
    ;;
    -npm=*|--npm_install=*)
    npm_option="${i#*=}"
    ;;
    --hotspot=*)
    hotspot_option="${i#*=}"
    shift
    ;;
    *)
    # unknown option
    echo "Option ${i#*=} unknown"
    ;;
esac
done

function validate_cgm ()
{
    # Conver to lowercase
    local selection="${1,,}"

    if [[ $selection =~ "g4-upload" || $selection =~ "g4-local-only" ]]; then
        echo "Unsupported CGM.  CGM=G4-upload has been replaced by CGM=G4-go (default). Please change your CGM in oref0-runagain.sh, or run interactive setup."
        echo
        return 1
    fi

    # TODO: Compare against list of supported CGMs
    # list of CGM supported by oref0 0.7.x: "g4-go", "g5", "g5-upload", "G6", "G6-upload", "mdt", "shareble", "xdrip", "xdrip-js"

    if ! [[ $selection =~ "g4-go" || $selection =~ "g5" || $selection =~ "g5-upload" || ${CGM,,} =~ "g6" || ${CGM,,} =~ "g6-upload" || $selection =~ "mdt" || $selection =~ "xdrip" || $selection =~ "xdrip-js" ]]; then
        echo "Unsupported CGM.  Please select (Dexcom) G4-go (default), G5, G5-upload, G6, G6-upload, MDT, xdrip, or xdrip-js."
        echo
        return 1
    fi

}

function validate_g4share_serial ()
{
    if [[ -z "$1" ]]; then
        echo Dexcom G4 Share serial not provided: continuing
        return 1
    else
        if [[ $1 == SM???????? ]]; then
            return 0
        else
            echo Dexcom G4 Share serial numbers are of the form SM????????
            return 1
        fi
    fi
}

function validate_g5transmitter_serial ()
{
    if [[ -z "$1" ]]; then
        echo Dexcom G5 transmitter serial not provided: continuing
        return 1
    else
        #TODO: actually validate the DEXCOM_CGM_TX_ID if provided
        return 0
    fi
}

function validate_ttyport ()
{
    true #TODO
}

function validate_pump_serial ()
{
    if [[ -z "$1" ]]; then
        echo Pump serial number is required.
        return 1
    fi
}

function validate_nightscout_host ()
{
    if [[ -z "$1" ]]; then
        echo Nightscout is required for interactive setup.
        return 1
    fi
}

function validate_nightscout_token ()
{
    true #TODO
}

function validate_api_secret ()
{
    if [[ -z "$1" ]]; then
        echo API_SECRET is required for interactive setup.
        return 1
    fi
}

function validate_bt_mac ()
{
    true #TODO
}

function validate_bt_peb ()
{
    true #TODO
}

function validate_max_iob ()
{
    true #TODO
}

function validate_pushover_token ()
{
    true #TODO
}

function validate_pushover_user ()
{
    true #TODO
}

function validate_ble_mac ()
{
    true #TODO
}

# Usage: do_openaps_import <file.json>
# Import aliases, devices, and reports from a JSON file into OpenAPS. What this
# means in practice is adding entries top openaps.ini, and creating other ini
# files for devices in the myopenaps directory.
function do_openaps_import ()
{
    cd $directory || die "Can't cd $directory"
    echo "Importing $1"
    cat "$1" |openaps import ||die "Could not import $1"
}

function remove_all_openaps_aliases ()
{
    local ALIASES="$(openaps alias show |cut -f 1 -d ' ')"
    for ALIAS in ALIASES; do
        openaps alias remove "$ALIAS" >/dev/null 2>&1
    done
}

# Usage: add_to_crontab <duplicate-detect-key> <schedule> <command>
# Checks cron for a line containing duplicate-detect-key. If there is no such
# line, appends the given command with the given schedule to crontab.
function add_to_crontab () {
    (crontab -l; crontab -l |grep -q "$1" || echo "$2" "$3") | crontab -
}

function request_stop_local_binary () {
    if [[ -x /usr/local/bin/$1 ]]; then
        if pgrep -x $1 > /dev/null; then
            if prompt_yn "Need to stop $1 to complete installation. OK?" y; then
                pgrep -x $1 | xargs kill
            fi
        fi
    fi
}

function copy_go_binaries () {
    for gobinary in $HOME/go/bin/*; do
        request_stop_local_binary `basename $gobinary`
    done
    request_stop_local_binary Go-mmtune

    cp -prv $HOME/go/bin/* /usr/local/bin/ || die "Couldn't copy go/bin"
}

function move_mmtune () {
    request_stop_local_binary Go-mmtune
    if [ -f /usr/local/bin/mmtune ]; then
      mv /usr/local/bin/mmtune /usr/local/bin/Go-mmtune || die "Couldn't move mmtune to Go-mmtune"
    else
      die "Couldn't move_mmtune() because /usr/local/bin/mmtune exists"
    fi
}

function install_or_upgrade_nodejs () {
    # install/upgrade to latest node 8 if neither node 8 nor node 10+ LTS are installed
    if ! nodejs --version | grep -e 'v8\.' -e 'v1[02468]\.' >/dev/null; then
        echo Installing node 8
        # Use nodesource setup script to add nodesource repository to sources.list.d
        sudo bash -c "curl -sL https://deb.nodesource.com/setup_8.x | bash -" || die "Couldn't setup node 8"
        # Install nodejs and npm from nodesource
        sudo apt-get install -y nodejs=8.* || die "Couldn't install nodejs"
    fi

    # Check that the nodejs you have installed is not broken. In particular, we're
    # checking for a problem with nodejs binaries that are present in the apt-get
    # repo for RaspiOS builds from mid-2021 and earlier, where the node interpreter
    # works, but has a 10x slower startup than expected (~30s on Pi Zero W
    # hardware, as opposed to ~3s using a statically-linked binary of the same
    # binary sourced from nvm).
    sudo apt-get install -y time
    NODE_EXECUTION_TIME="$(\time --format %e node -e 'true' 2>&1)"
    if [ 1 -eq "$(echo "$NODE_EXECUTION_TIME > 10" |bc)" ]; then
        echo "Your installed nodejs ($(node --version)) is very slow to start (took ${NODE_EXECUTION_TIME}s)"
        echo "This is a known problem with certain versions of Raspberry Pi OS."

        if prompt_yn "Install a new nodejs version using nvm?" Y; then
            echo "Installing nvm and using it to replace the system-provided nodejs"
    
            # Download nvm
            curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
            # Run nvm, adding its aliases to this shell
            source ~/.nvm/nvm.sh
            # Use nvm to install nodejs
            nvm install 10.24.1
            # Symlink node into /usr/local/bin, where it will shadow /usr/bin/node
            ln -s ~/.nvm/versions/node/v10.24.1/bin/node /usr/local/bin/node

            NEW_NODE_EXECUTION_TIME="$(\time --format %e node -e 'true' 2>&1)"
            echo "New nodejs took ${NEW_NODE_EXECUTION_TIME}s to start"
        fi
    else
        echo "Your installed nodejs version is OK."
    fi
}

if ! validate_cgm "${CGM}"; then
    DIR="" # to force a Usage prompt
fi
if [[ -z "$DIR" || -z "$serial" ]]; then
    print_usage
    if ! prompt_yn "Start interactive setup?" Y; then
        exit
    fi
    echo
    if [[ -z $DIR ]]; then
        DIR="$HOME/myopenaps"
    fi
    directory="$(readlink -m $DIR)"
    echo

    prompt_and_validate serial "What is your pump serial number (six digits, numbers only)?" validate_pump_serial
    echocolor "Ok, $serial it is."
    echo

    echo "What kind of CGM would you like to configure for offline use? Options are:"
    echo "G4-Go: will use and upload BGs from a plugged in or BLE-paired G4 receiver to Nightscout"
    echo "G5: will use BGs from a plugged in G5, but will *not* upload them (the G5 app usually does that)"
    echo "G5-upload: will use and upload BGs from a plugged in G5 receiver to Nightscout"
    echo "G6: will use BGs from a plugged in G5/G6 touchscreen receiver, but will *not* upload them (the G6 app usually does that)"
    echo "G6-upload: will use and upload BGs from a plugged in G5/G6 touchscreen receiver to Nightscout"
    echo "MDT: will use and upload BGs from an Enlite sensor paired to your pump"
    echo "xdrip: will work with an xDrip receiver app on your Android phone"
    echo "xdrip-js: will work directly with a Dexcom G5/G6 transmitter and will upload to Nightscout"
    echo "Note: no matter which option you choose, CGM data will also be downloaded from NS when available."
    echo
    prompt_and_validate CGM "What kind of CGM would you like to configure?:" validate_cgm
    echocolor "Ok, $CGM it is."
    echo
    if [[ ${CGM,,} =~ "g4-go" ]]; then
        prompt_and_validate BLE_SERIAL "If your G4 has Share, what is your G4 Share Serial Number? (i.e. SM12345678)" validate_g4share_serial ""
        BLE_SERIAL=$REPLY
        echo "$BLE_SERIAL? Got it."
        echo
    fi
    if [[ ${CGM,,} =~ "xdrip-js" ]]; then
        prompt_and_validate DEXCOM_CGM_TX_ID "What is your current Dexcom Transmitter ID?" validate_g5transmitter_serial
        echo "$DEXCOM_CGM_TX_ID? Got it."
        echo
    fi

    # Decision tree for hardware setup to give finer-grained control over setup automation.
    # Passes $hardwaretype (default is explorer-board) to the rest of setup.
    if grep -qa "Explorer HAT" /proc/device-tree/hat/product &>/dev/null ; then
        # Autodetect and set up Explorer HAT
        echocolor "Explorer Board HAT detected. "
        echocolor "Configuring for Explorer Board HAT. "
        ttyport=/dev/spidev0.0
        hardwaretype=explorer-hat
        radiotags="cc111x"
    elif is_edison; then # Options for Edison (Explorer Board is default)
        echo "What kind of hardware setup do you have? Options are:"
        echo "1) Explorer Board"
        echo "2) TI stick (SPI-connected)"
        echo "3) Other Radio (DIY: rfm69, cc11xx)"
        read -p "Please enter the number for your hardware configuration: [1] " -r
        case $REPLY in
          2) echocolor "Configuring for SPI-connected TI stick. "; ttyport=/dev/spidev0.0; hardwaretype=386-spi; radiotags="cc111x";;
          3)
             prompt_and_validate ttyport "What is your TTY port? (/dev/ttySOMETHING)" validate_ttyport
             echocolor "Ok, we'll try TTY $ttyport then. "; echocolor "You will need to pick your radio type. "; hardwaretype=diy;;
          *) echocolor "Yay! Configuring for Edison with Explorer Board. "; ttyport=/dev/spidev5.1; hardwaretype=edison-explorer; radiotags="cc111x";;
        esac
    elif is_pi; then # Options for raspberry pi, including Explorer HAT (default) if it's not auto-detected
        echo "What kind of hardware setup do you have? Options are:"
        echo "1) Explorer HAT"
        echo "2) Radiofruit RFM69HCW Bonnet"
        echo "3) RFM69HCW (DIY: SPI)"
        echo "4) TI Stick (SPI-connected)"
        echo "5) Other radio (DIY: rfm69, cc11xx)"
        read -p "Please enter the number for your hardware configuration: [1] " -r
        case $REPLY in
          2) echocolor "Configuring Radiofruit RFM69HCW Bonnet. "; ttyport=/dev/spidev0.1; hardwaretype=radiofruit; radiotags="rfm69";;
          3) echocolor "Configuring RFM69HCW. "; hardwaretype=diy;;
          4) echocolor "Configuring for SPI-connected TI stick. "; ttyport=/dev/spidev0.0; hardwaretype=arm-spi; radiotags="cc111x";;
          5)
             prompt_and_validate ttyport "What is your TTY port? (/dev/ttySOMETHING)" validate_ttyport
             echocolor "Ok, we'll try TTY $ttyport then. "; echocolor "You will need to pick your radio type. "; hardwaretype=diy;;
          *) echocolor "Configuring Explorer Board HAT. "; ttyport=/dev/spidev0.0; hardwaretype=explorer-hat; radiotags="cc111x";;
        esac
    else # If Edison or raspberry pi aren't detected, ask the user for their tty port
        echo "Cannot auto-detect a supported platform (Edison or Raspberry Pi). Please make sure user 'edison' or 'pi' exists, or continue setup with manual configuration. "
        prompt_and_validate ttyport "What is your TTY port? (/dev/ttySOMETHING)" validate_ttyport
        echocolor "Ok, we'll try TTY $ttyport then. "
        echocolor "You will need to pick your radio type."
        hardwaretype=diy
    fi

    # Get details from the user about how binaries should be built. Default is cc111x.
    if [ $hardwaretype = diy ]; then
        echo "What type of radio are you using? Options are:"
        echo "1) cc1110 or cc1111"
        echo "2) cc1101"
        echo "3) RFM69HCW on /dev/spidev0.0 (walrus)"
        echo "4) RFM69HCW on /dev/spidev0.1 (radiofruit bonnet)"
        echo "5) Enter radiotags manually"
        read -p "Please enter the number for your radio configuration: [1] " -r
        case $REPLY in
          2) radiotags="cc1101";;
          3) radiotags="rfm69 walrus"; ttyport=/dev/spidev0.0;;
          4) radiotags="rfm69"; ttyport=/dev/spidev0.1;;
          5) read -p "Enter your radiotags: " -r; radiotags=$REPLY;;
          *) radiotags="cc111x";;
        esac
        echo "Building Go pump binaries with " + "$radiotags" + " tags."
    else
      echo "Building Go pump binaries with " + "$radiotags" + " tags."
#      ecc1medtronicversion="latest"
#      ecc1dexcomversion="latest"
    fi

#TODO: add versioning support
#    read -p "You could either build the Medtronic library from latest version, or type the version tag you would like to use, example 'v2019.01.21' [S]/<version> " -r
#    if [[ $REPLY =~ ^[Vv]$ ]]; then
#      ecc1medtronicversion="tags/$REPLY"
#      echo "Will use https://github.com/ecc1/medtronic/releases/$REPLY."
#      read -p "Also enter the ecc1/dexcom version, example 'v2018.12.05' <version> " -r
#      ecc1dexcomversion="tags/$REPLY"
#      echo "Will use https://github.com/ecc1/dexcom/$REPLY if Go-dexcom is needed."
#    else 
#      echo "Okay, building Medtronic library from latest version."
#    fi

    if [[ ! -z "${ttyport}" ]]; then
      echo -e "\e[1mMedtronic pumps come in two types: WW (Worldwide) pumps, and NA (North America) pumps.\e[0m"
      echo "Confusingly, North America pumps may also be used outside of North America."
      echo
      echo "USA pumps have a serial number / model number that has 'NA' in it."
      echo "Non-USA pumps have a serial number / model number that 'WW' in it."
      echo
      echo -e "\e[1mAre you using a USA/North American pump? If so, just hit enter. Otherwise enter WW: \e[0m"
      read -r
      radio_locale=$REPLY
      echo -n "Ok, "
      # Force uppercase, just in case the user entered ww
      radio_locale=${radio_locale^^}

      if [[ -z "${radio_locale}" ]]; then
          radio_locale='US'
      fi

      echocolor "${radio_locale} it is"
      echo
    fi

    prompt_and_validate REPLY "What is your Nightscout site? (i.e. https://mynightscout.herokuapp.com)?" validate_nightscout_host
    # remove any trailing / from NIGHTSCOUT_HOST
    NIGHTSCOUT_HOST=$(echo $REPLY | sed 's/\/$//g')
    echocolor "Ok, $NIGHTSCOUT_HOST it is."
    echo
    if [[ ! -z $NIGHTSCOUT_HOST ]]; then
        echo "Starting with oref 0.5.0 you can use token based authentication to Nightscout. This makes it possible to deny anonymous access to your Nightscout instance. It's more secure than using your API_SECRET, but must first be configured in Nightscout."
        if prompt_yn "Do you want to use token based authentication? (Enter 'N' to provide your Nightscout secret instead)" N; then
            prompt_and_validate REPLY "What Nightscout access token (i.e. subjectname-hashof16characters) do you want to use for this rig?" validate_nightscout_token
            API_SECRET="token=${REPLY}"
            echocolor "Ok, $API_SECRET it is."
            echo
        else
            echocolor "Ok, you'll use API_SECRET instead."
            echo
            prompt_and_validate API_SECRET "What is your Nightscout API_SECRET (i.e. myplaintextsecret; It should be at least 12 characters long)?" validate_api_secret
            echocolor "Ok, $API_SECRET it is."
            echo
        fi
    fi

    if prompt_yn "Do you want to be able to set up BT tethering?" N; then
        prompt_and_validate BT_MAC "What is your phone's BT MAC address (i.e. AA:BB:CC:DD:EE:FF)?" validate_bt_mac
        echo
        echocolor "Ok, $BT_MAC it is. You will need to follow directions in docs to set-up BT tether after your rig is successfully looping."
        echo
    else
        echo
        echocolor "Ok, no BT installation at this time, you can run this script again later if you change your mind."
        echo
    fi

    if prompt_yn "Do you want to be able to set up a local-only wifi hotspot for offline monitoring?" N; then
        HOTSPOT=true
    else
        HOTSPOT=false
    fi

    if [[ ! -z $BT_PEB ]]; then
        prompt_and_validate BT_PEB "For Pancreabble enter Pebble mac id (i.e. AA:BB:CC:DD:EE:FF) hit enter to skip" validate_bt_peb
        BT_PEB=$REPLY
        echocolor "Ok, $BT_PEB it is."
        echo
    fi

    echo
    echo -e "\e[1mWhat value would you like to set for your max_IOB? Context: max_IOB is a safety setting\e[0m"
    echo
    echo -e "\e[3mIt limits how much insulin OpenAPS can give you in addition to your manual boluses and pre-set basal rates.\e[0m"
    echo
    echo -e 'max_IOB of 0 will make it so OpenAPS cannot provide positive IOB, and will function as "low glucose suspend" type mode.'
    echo
    echo -e "\e[4mIf you are unsure of what you would like max_IOB to be, we recommend starting with either 0 or one hour worth of basals.\e[0m"
    echo
    echo -e "\e[3mRead the docs for more tips on how to determine a max_IOB that is right for you. (You can edit this in ~/myopenaps/preferences.json later).\e[0m"
    echo
    prompt_and_validate REPLY "Type a whole number (without a decimal) [i.e. 0] and hit enter:" validate_max_iob
      if [[ $REPLY =~ [0-9] ]]; then
        max_iob="$REPLY"
        echocolor "Ok, $max_iob units will be set as your max_iob."
        echo
      else
        max_iob=0
        echocolor "Ok, your max_iob will be set to 0 for now."
        echo
      fi

    if prompt_yn "Enable autotuning of basals and ratios?" Y; then
       ENABLE+=" autotune "
       echocolor "Ok, autotune will be enabled. It will run around 4am."
       echo
    else
       echocolor "Ok, no autotune."
       echo
    fi

    #always enabling AMA by default
    #ENABLE+=" meal "

    if prompt_yn "Do you want to enable carbsReq Pushover alerts?" N; then
        prompt_and_validate PUSHOVER_TOKEN "If so, what is your Pushover API Token?" validate_pushover_token
        echocolor "Ok, Pushover token $PUSHOVER_TOKEN it is."
        echo

        prompt_and_validate PUSHOVER_USER "And what is your Pushover User Key?" validate_pushover_user
        echocolor "Ok, Pushover User Key $PUSHOVER_USER it is."
        echo
    else
        echocolor "Ok, no Pushover for you."
        echo
    fi

    echo
    echo
    echo

fi

echo -n "Setting up oref0 in $directory for pump $serial with $CGM CGM, "
if [[ ! -z $BLE_SERIAL ]]; then
    echo -n "G4 Share serial $BLE_SERIAL, "
fi
if [[ ! -z $DEXCOM_CGM_TX_ID ]]; then
    echo -n "G5 transmitter serial $DEXCOM_CGM_TX_ID, "
fi
echo
echo -n "NS host $NIGHTSCOUT_HOST, "

if [[ -z "$ttyport" ]]; then
    echo -n Carelink
else
    echo -n TTY $ttyport
fi
if [[ "$max_iob" != "0" ]]; then
    echo -n ", max_iob $max_iob";
fi
if [[ ! -z "$max_daily_safety_multiplier" ]]; then
    echo -n ", max_daily_safety_multiplier $max_daily_safety_multiplier";
fi
if [[ ! -z "$current_basal_safety_multiplier" ]]; then
    echo -n ", current_basal_safety_multiplier $current_basal_safety_multiplier";
fi
#if [[ ! -z "$bolussnooze_dia_divisor" ]]; then
    #echo -n ", bolussnooze_dia_divisor $bolussnooze_dia_divisor";
#fi
if [[ ! -z "$min_5m_carbimpact" ]]; then
    echo -n ", min_5m_carbimpact $min_5m_carbimpact";
fi
if [[ ! -z "$ENABLE" ]]; then
    echo -n ", advanced features $ENABLE";
fi
echo
echo

# This section is echoing (commenting) back the options you gave it during the interactive setup script.
# The "| tee -a /tmp/oref0-runagain.sh" part is also appending it to a file so you can run it again more easily in the future.

# create temporary file for oref0-runagain.sh
OREF0_RUNAGAIN=`mktemp /tmp/oref0-runagain.XXXXXXXXXX`
echo "#!/usr/bin/env bash" > $OREF0_RUNAGAIN
echo "# To run again with these same options, use: " | tee $OREF0_RUNAGAIN
echo -n "$HOME/src/oref0/bin/oref0-setup.sh --dir=$directory --serial=$serial --cgm=$CGM" | tee -a $OREF0_RUNAGAIN
if [[ ! -z $BLE_SERIAL ]]; then
    echo -n " --bleserial=$BLE_SERIAL" | tee -a $OREF0_RUNAGAIN
fi
echo -n " --ns-host=$NIGHTSCOUT_HOST --api-secret=$API_SECRET" | tee -a $OREF0_RUNAGAIN
if [[ ! -z "$ttyport" ]]; then
    echo -n " --tty=$ttyport" | tee -a $OREF0_RUNAGAIN
fi
echo -n " --max_iob=$max_iob" | tee -a $OREF0_RUNAGAIN;
if [[ ! -z "$max_daily_safety_multiplier" ]]; then
    echo -n " --max_daily_safety_multiplier=$max_daily_safety_multiplier" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$current_basal_safety_multiplier" ]]; then
    echo -n " --current_basal_safety_multiplier=$current_basal_safety_multiplier" | tee -a $OREF0_RUNAGAIN
fi
#if [[ ! -z "$bolussnooze_dia_divisor" ]]; then
    #echo -n " --bolussnooze_dia_divisor=$bolussnooze_dia_divisor" | tee -a $OREF0_RUNAGAIN
#fi
if [[ ! -z "$min_5m_carbimpact" ]]; then
    echo -n " --min_5m_carbimpact=$min_5m_carbimpact" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$ENABLE" ]]; then
    echo -n " --enable='$ENABLE'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$radio_locale" ]]; then
    echo -n " --radio_locale='$radio_locale'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$BLE_MAC" ]]; then
    echo -n " --blemac='$BLE_MAC'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$DEXCOM_CGM_TX_ID" ]]; then
    echo -n " --dexcom_tx_sn='$DEXCOM_CGM_TX_ID'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$BT_MAC" ]]; then
    echo -n " --btmac='$BT_MAC'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$BT_PEB" ]]; then
    echo -n " --btpeb='$BT_PEB'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$PUSHOVER_TOKEN" ]]; then
    echo -n " --pushover_token='$PUSHOVER_TOKEN'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$PUSHOVER_USER" ]]; then
    echo -n " --pushover_user='$PUSHOVER_USER'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$hardwaretype" ]]; then
    echo -n " --hardwaretype='$hardwaretype'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$radiotags" ]]; then
    echo -n " --radiotags='$radiotags'" | tee -a $OREF0_RUNAGAIN
fi
if [[ ! -z "$hotspot_option" ]]; then
    echo -n " --hotspot='$hotspot_option'" | tee -a $OREF0_RUNAGAIN
fi
echo; echo | tee -a $OREF0_RUNAGAIN
chmod 755 $OREF0_RUNAGAIN

# End of interactive setup

echocolor -n "Continue?"
if prompt_yn "" N; then

    # Having the loop run in the background during setup slows things way down and lengthens the time before first loop
    service cron stop
    # Kill oref0-pump-loop
    pkill -f oref0-pump-loop

    # Workaround for Jubilinux v0.2.0 (Debian Jessie) migration to LTS
    if is_debian_jessie; then
        # Disable valid-until check for archived Debian repos (expired certs)
        echo "Acquire::Check-Valid-Until false;" | tee -a /etc/apt/apt.conf.d/10-nocheckvalid
        # Replace apt sources.list with archive.debian.org locations
        echo -e "deb http://security.debian.org/ jessie/updates main\n#deb-src http://security.debian.org/ jessie/updates main\n\ndeb http://archive.debian.org/debian/ jessie-backports main\n#deb-src http://archive.debian.org/debian/ jessie-backports main\n\ndeb http://archive.debian.org/debian/ jessie main contrib non-free\n#deb-src http://archive.debian.org/debian/ jessie main contrib non-free" > /etc/apt/sources.list
    fi
    
    #Mount the Edison's fat32 partition at /usr/local/go to give us lots of room to install golang
    if is_edison && [ -e /dev/mmcblk0p9 ] && ! mount | grep -qa mmcblk0p9 ; then
        echo 'Removing golang from /usr partition...' && rm -rf /usr/local/go && mkdir -p /usr/local/go
        if ! grep -qa "mmcblk0p9" /etc/fstab ; then
          echo 'Adding Edison FAT32 partition to /etc/fstab...' && echo "/dev/mmcblk0p9 /usr/local/go auto defaults 1 1" >> /etc/fstab
        fi
        echo 'Mounting Edison FAT32 partition...' && mount -a
    fi
    
    #TODO: remove this when IPv6 works reliably
    echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4

    # update, upgrade, and autoclean apt-get
    if file_is_recent /var/lib/apt/periodic/update-stamp 3600; then
        echo apt-get update-stamp is recent: skipping
    else
        echo Running apt-get update
        sudo apt-get update
    fi
    if file_is_recent /var/lib/apt/periodic/upgrade-stamp 3600; then
        echo apt-get upgrade-stamp is recent: skipping
    else
        echo Running apt-get upgrade
        sudo apt-get -y upgrade
        # make sure hostapd and dnsmasq don't get re-enabled
        update-rc.d -f hostapd remove
        update-rc.d -f dnsmasq remove
    fi
    echo Running apt-get autoclean
    sudo apt-get autoclean

    install_or_upgrade_nodejs

    # Attempting to remove git to make install --nogit by default for existing users
    echo Removing any existing git in $directory/.git
    rm -rf $directory/.git
    echo Removed any existing git
    echo "Uninstalling parsedatetime, reinstalling correct version"
    pip uninstall -y parsedatetime && pip install -I parsedatetime==2.5
    # TODO: delete this after openaps 0.2.2 release
    echo Checking openaps 0.2.2 installation with --nogit support
    if ! openaps --version 2>&1 | egrep "0.[2-9].[2-9]"; then
        echo Installing latest openaps w/ nogit && sudo pip install --default-timeout=1000 git+https://github.com/openaps/openaps.git@nogit || die "Couldn't install openaps w/ nogit"
    fi

    #Make sure the directory is valid
    echo -n "Checking $directory: "
    mkdir -p $directory
    if openaps init $directory --nogit; then
        echo $directory initialized
    else
        die "Can't init $directory"
    fi
    cd $directory || die "Can't cd $directory"

    # Clear out any OpenAPS aliases from previous versions (they'll get
    # recreated if they're still used)
    remove_all_openaps_aliases

    # Taking the oref0-runagain.sh from tmp to $directory
    mv $OREF0_RUNAGAIN ./oref0-runagain.sh

    # Make sure it is executable afterwards
    chmod +x ./oref0-runagain.sh

    mkdir -p monitor || die "Can't mkdir monitor"
    mkdir -p raw-cgm || die "Can't mkdir raw-cgm"
    mkdir -p cgm || die "Can't mkdir cgm"
    mkdir -p settings || die "Can't mkdir settings"
    mkdir -p enact || die "Can't mkdir enact"
    mkdir -p upload || die "Can't mkdir upload"
    if [[ ${CGM,,} =~ "xdrip" || ${CGM,,} =~ "xdrip-js" ]]; then
        mkdir -p xdrip || die "Can't mkdir xdrip"
    fi
    mkdir -p $HOME/src/
    if [ -d "$HOME/src/oref0/" ]; then
        echo "$HOME/src/oref0/ already exists; pulling latest"
        (cd $HOME/src/oref0 && git fetch && git pull) || (
            if ! prompt_yn "Couldn't pull latest oref0. Continue anyways?"; then
                die "Failed to update oref0."
            fi
        )
    else
        echo -n "Cloning oref0: "
        (cd $HOME/src && git clone https://github.com/openaps/oref0.git) || die "Couldn't clone oref0"
    fi

    # Make sure jq version >1.5 is installed
    if is_debian_jessie; then
        sudo apt-get -y -t jessie-backports install jq
    else
        sudo apt-get -y install jq
    fi

    echo Checking oref0 installation
    cd $HOME/src/oref0
    if git branch | grep "* master"; then
        npm list -g --depth=0 | egrep oref0@0.6.[0] || (echo Installing latest oref0 package && sudo npm install -g oref0)
    elif [[ ${npm_option,,} == "force" ]]; then
        echo Forcing install of latest oref0 from $HOME/src/oref0/ && cd $HOME/src/oref0/ && npm run global-install
    else
        npm list -g --depth=0 | egrep oref0@0.6.[1-9] || (echo Installing latest oref0 from $HOME/src/oref0/ && cd $HOME/src/oref0/ && npm run global-install)
    fi

    cd $directory || die "Can't cd $directory"

    echo Checking mmeowlink installation
    if openaps vendor add --path . mmeowlink.vendors.mmeowlink 2>&1 | grep "No module"; then
        pip show mmeowlink | egrep "Version: 0.11.1" || (
            echo Installing latest mmeowlink
            sudo pip install --default-timeout=1000 -U mmeowlink || die "Couldn't install mmeowlink"
        )
    fi

    test -f preferences.json && cp preferences.json old_preferences.json || echo "No old preferences.json to save off"
    if [[ "$max_iob" == "0" && -z "$max_daily_safety_multiplier" && -z "$current_basal_safety_multiplier" && -z "$min_5m_carbimpact" ]]; then
        oref0-get-profile --exportDefaults > preferences.json || die "Could not run oref0-get-profile"
    else
        preferences_from_args=()
        if [[ "$max_iob" != "0" ]]; then
            preferences_from_args+="\"max_iob\":$max_iob "
        fi
        if [[ ! -z "$max_daily_safety_multiplier" ]]; then
            preferences_from_args+="\"max_daily_safety_multiplier\":$max_daily_safety_multiplier "
        fi
        if [[ ! -z "$current_basal_safety_multiplier" ]]; then
            preferences_from_args+="\"current_basal_safety_multiplier\":$current_basal_safety_multiplier "
        fi
        #if [[ ! -z "$bolussnooze_dia_divisor" ]]; then
            #preferences_from_args+="\"bolussnooze_dia_divisor\":$bolussnooze_dia_divisor "
        #fi
        if [[ ! -z "$min_5m_carbimpact" ]]; then
            preferences_from_args+="\"min_5m_carbimpact\":$min_5m_carbimpact "
        fi
        function join_by { local IFS="$1"; shift; echo "$*"; }
        # merge existing preferences with preferences from arguments. (preferences from arguments take precedence)
        echo "{ $(join_by , ${preferences_from_args[@]}) }" > arg_prefs.json
        if [[ -s preferences.json ]]; then
            cat arg_prefs.json | jq --slurpfile existing_prefs preferences.json '$existing_prefs[0] + .' > updated_prefs.json && rm arg_prefs.json
        else
            mv arg_prefs.json updated_prefs.json
        fi
        oref0-get-profile --updatePreferences updated_prefs.json > preferences.json && rm updated_prefs.json || die "Could not run oref0-get-profile"
    fi

    # Save information to preferences.json
    # Starting from 0.7.x all preferences for oref0 will be stored in this file, along with some hardware configurations
    set_pref_string .nightscout_host "$NIGHTSCOUT_HOST"
    set_pref_string .cgm "${CGM,,}"
    set_pref_string .enable "$ENABLE"
    set_pref_string .ttyport "$ttyport"
    set_pref_string .myopenaps_path "$directory"
    set_pref_string .pump_serial "$serial"
    set_pref_string .radio_locale "$radio_locale"
    set_pref_string .hardwaretype "$hardwaretype"
    if [[ ! -z "$BT_PEB" ]]; then
        set_pref_string .bt_peb "$BT_PEB"
    fi
    if [[ ! -z "$BT_MAC" ]]; then
        set_pref_string .bt_mac "$BT_MAC"
    fi
    if [[ ! -z "$PUSHOVER_TOKEN" ]]; then
        set_pref_string .pushover_token "$PUSHOVER_TOKEN"
    fi
    if [[ ! -z "$PUSHOVER_USER" ]]; then
        set_pref_string .pushover_user "$PUSHOVER_USER"
    fi
    # TODO: API_SECRET has not been converted to using preference.json yet. Convert API_SECRET to .nightscout_api_secret or .nightscout_hashed_api_secret
    # The Nightscout API_SECRET (admin password) should not be written in plain text, but in a hashed form
    # set_pref_string .nightscout_api_secret "$API_SECRET"

    if [[ ${CGM,,} =~ "g4-go" || ${CGM,,} =~ "g5" || ${CGM,,} =~ "g5-upload" || ${CGM,,} =~ "g6" || ${CGM,,} =~ "g6-upload" ]]; then
        set_pref_string .cgm_loop_path "$directory"
    fi

    if [[ ${CGM,,} =~ "xdrip" ]]; then # Evaluates true for both xdrip and xdrip-js 
        set_pref_string .xdrip_path "$HOME/.xDripAPS"
        set_pref_string .bt_offline "true"
    fi
    #if [[ ! -z "$DEXCOM_CGM_TX_ID" ]]; then
        #set_pref_string .dexcom_cgm_tx_id "$DEXCOM_CGM_TX_ID"
    #fi

    cat preferences.json

    # fix log rotate file
    sed -i "s/weekly/hourly/g" /etc/logrotate.conf
    sed -i "s/daily/hourly/g" /etc/logrotate.conf
    sed -i "s/#compress/compress/g" /etc/logrotate.conf

    # enable log rotation
    sudo cp $HOME/src/oref0/logrotate.openaps /etc/logrotate.d/openaps || die "Could not cp /etc/logrotate.d/openaps"
    sudo cp $HOME/src/oref0/logrotate.rsyslog /etc/logrotate.d/rsyslog || die "Could not cp /etc/logrotate.d/rsyslog"

    test -d /var/log/openaps || sudo mkdir /var/log/openaps && sudo chown $USER /var/log/openaps || die "Could not create /var/log/openaps"

    if [[ -f /etc/cron.daily/logrotate ]]; then
        mv -f /etc/cron.daily/logrotate /etc/cron.hourly/logrotate
    fi

    if [[ -f /etc/cron.daily/logrotate ]]; then
        mv -f /etc/cron.daily/logrotate /etc/cron.hourly/logrotate
    fi

    if ! grep -qa "kernel.panic" /etc/sysctl.conf ; then
      echo -e "# reboot rig 3 seconds after a kernel panic\nkernel.panic = 3" >> /etc/sysctl.conf
    fi

    # configure ns
    if [[ ! -z "$NIGHTSCOUT_HOST" && ! -z "$API_SECRET" ]]; then
        echo "Removing any existing ns device: "
        ( killall -g openaps; killall-g oref0-pump-loop) 2>/dev/null; openaps device remove ns 2>/dev/null
        echo "Running nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET"
        nightscout autoconfigure-device-crud $NIGHTSCOUT_HOST $API_SECRET || die "Could not run nightscout autoconfigure-device-crud"
        if [[ "${API_SECRET,,}" =~ "token=" ]]; then # install requirements for token based authentication
            sudo apt-get -y install python3-pip
            sudo pip3 install --default-timeout=1000 requests || die "Can't add pip3 requests - error installing"
            oref0_nightscout_check || die "Error checking Nightscout permissions"
        fi
    fi

    # import template
    do_openaps_import $HOME/src/oref0/lib/oref0-setup/vendor.json
    do_openaps_import $HOME/src/oref0/lib/oref0-setup/device.json
    do_openaps_import $HOME/src/oref0/lib/oref0-setup/report.json
    do_openaps_import $HOME/src/oref0/lib/oref0-setup/alias.json

    #Check to see if we need to install bluetooth
    echo Checking for BT Mac, BT Peb, Shareble, or xdrip-js
    if [[ ! -z "$BT_PEB" || ! -z "$BT_MAC" || ! -z $BLE_SERIAL || ! -z $DEXCOM_CGM_TX_ID ]]; then
        # Install Bluez for BT Tethering
        echo Checking bluez installation
        bluetoothdversion=$(bluetoothd --version || 0)
        # use packaged bluez with Debian Stretch (Jubilinux 0.3.0 and Raspbian)
        bluetoothdminversion=5.43
        bluetoothdversioncompare=$(awk 'BEGIN{ print "'$bluetoothdversion'"<"'$bluetoothdminversion'" }')
        if [ "$bluetoothdversioncompare" -eq 1 ]; then
            cd $HOME/src/ && wget -c4 https://www.kernel.org/pub/linux/bluetooth/bluez-5.48.tar.gz && tar xvfz bluez-5.48.tar.gz || die "Couldn't download bluez"
            killall bluetoothd &>/dev/null #Kill current running version if its out of date and we are updating it
            cd $HOME/src/bluez-5.48 && ./configure --disable-systemd && make || die "Couldn't make bluez"
            killall bluetoothd &>/dev/null #Kill current running version if its out of date and we are updating it
            sudo make install || die "Couldn't make install bluez"
            killall bluetoothd &>/dev/null #Kill current running version if its out of date and we are updating it
            sudo cp ./src/bluetoothd /usr/local/bin/ || die "Couldn't install bluez"
            sudo apt-get install -y bluez-tools

            # Replace all other instances of bluetoothd and bluetoothctl to make sure we are always using the self-compiled version
            while IFS= read -r bt_location; do
                if [[ $($bt_location -v|awk -F': ' '{print ($NF < 5.48)?1:0}') -eq 1 ]]; then
                    # Find latest version of bluez under $HOME/src and copy it to locations which have a version of bluetoothd/bluetoothctl < 5.48
                    if [[ $(find $(find $HOME/src -name "bluez-*" -type d | sort -rn | head -1) -name bluetoothd -o -name bluetoothctl | wc -l) -eq 2 ]]; then
                        killall $(basename $bt_location) &>/dev/null #Kill current running version if its out of date and we are updating it
                        sudo cp -p $(find $(find $HOME/src -name "bluez-*" -type d | sort -rn | head -1) -name $(basename $bt_location)) $bt_location || die "Couldn't replace $(basename $bt_location) in $(dirname $bt_location)"
                        touch /tmp/reboot-required
                    else
                        echo "Latest version of bluez @ $(find $HOME/src -name "bluez-*" -type d | sort -rn | head -1) is missing or has extra copies of bluetoothd or bluetoothctl, unable to replace older binaries"
                    fi
                fi
            done < <(find / -name "bluetoothd" ! -path "*/src/bluez-*" ! -path "*.rootfs/*") # Find all locations with bluetoothctl or bluetoothd excluding directories with *bluez* in the path

            oref0-bluetoothup
        else
            echo bluez version ${bluetoothdversion} already installed
        fi
        if [[ ${hotspot_option,,} =~ "true" ]]; then
            echo Installing prerequisites and configs for local-only hotspot
            apt-get install -y hostapd dnsmasq || die "Couldn't install hostapd dnsmasq"
            test ! -f  /etc/dnsmasq.conf.bak && mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
            cp $HOME/src/oref0/headless/dnsmasq.conf /etc/dnsmasq.conf || die "Couldn't copy dnsmasq.conf"
            test ! -f  /etc/hostapd/hostapd.conf.bak && mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bak
            cp $HOME/src/oref0/headless/hostapd.conf /etc/hostapd/hostapd.conf || die "Couldn't copy hostapd.conf"
            sed -i.bak -e "s|DAEMON_CONF=$|DAEMON_CONF=/etc/hostapd/hostapd.conf|g" /etc/init.d/hostapd
            cp $HOME/src/oref0/headless/interfaces.ap /etc/network/ || die "Couldn't copy interfaces.ap"
            cp /etc/network/interfaces /etc/network/interfaces.client || die "Couldn't copy interfaces.client"
            if [ ! -z "$BT_MAC" ]; then
                printf 'Checking for the bnep0 interface in the interfaces.client file and adding if missing...'
                # Make sure the bnep0 interface is in the /etc/networking/interface
                (grep -qa bnep0 /etc/network/interfaces.client && printf 'skipped.\n') || (printf '\n%s\n\n' "iface bnep0 inet dhcp" >> /etc/network/interfaces.client && printf 'added.\n')
            fi
            #Stop automatic startup of hostapd & dnsmasq
            update-rc.d -f hostapd remove
            update-rc.d -f dnsmasq remove
            # Edit /etc/hostapd/hostapd.conf for wifi using Hostname
            sed -i.bak -e "s/ssid=OpenAPS/ssid=${HOSTNAME}/" /etc/hostapd/hostapd.conf
            # Add Commands to /etc/rc.local
            # Interrupt Kernel Messages
            if ! grep -q 'sudo dmesg -n 1' /etc/rc.local; then
                sed -i.bak -e '$ i sudo dmesg -n 1' /etc/rc.local
            fi
            # Add to /etc/rc.local to check if in hotspot mode and turn back to client mode during bootup
            if ! grep -q 'cp /etc/network/interfaces.client /etc/network/interfaces' /etc/rc.local; then
                sed -i.bak -e "$ i if [ -f /etc/network/interfaces.client ]; then\n\tif  grep -q '#wpa-' /etc/network/interfaces; then\n\t\tsudo ifdown wlan0\n\t\tsudo cp /etc/network/interfaces.client /etc/network/interfaces\n\t\tsudo ifup wlan0\n\tfi\nfi" /etc/rc.local || die "Couldn't modify /etc/rc.local"
            fi
        else
            echo Skipping local-only hotspot
        fi
    fi

    # add/configure devices
    if [[ ${CGM,,} =~ "g5" || ${CGM,,} =~ "g5-upload" ]]; then
        openaps use cgm config --G5
        openaps report add raw-cgm/raw-entries.json JSON cgm oref0_glucose --hours "24.0" --threshold "100" --no-raw
        set_pref_string .cgm_loop_path "$directory"
    elif [[ ${CGM,,} =~ "g6" || ${CGM,,} =~ "g6-upload" ]]; then
        openaps use cgm config --G6
        openaps report add raw-cgm/raw-entries.json JSON cgm oref0_glucose --hours "24.0" --threshold "100" --no-raw
        set_pref_string .cgm_loop_path "$directory"
    fi

        #This is done to make sure other programs don't break. As of 0.7.0, OpenAPS itself no longer uses pump.ini
        echo '[device "pump"]' > pump.ini
        echo "serial = $serial" >> pump.ini
        echo "radio_locale = $radio_locale" >> pump.ini
    #fi

    # Medtronic CGM
    #if [[ ${CGM,,} =~ "mdt" ]]; then
    #    sudo pip install --default-timeout=1000 -U openapscontrib.glucosetools || die "Couldn't install glucosetools"
    #    openaps device remove cgm 2>/dev/null
    #    if [[ -z "$ttyport" ]]; then
    #        openaps device add cgm medtronic $serial || die "Can't add cgm"
    #    else
    #        openaps device add cgm mmeowlink subg_rfspy $ttyport $serial $radio_locale || die "Can't add cgm"
    #    fi
    #    do_openaps_import $HOME/src/oref0/lib/oref0-setup/mdt-cgm.json
    #fi

    sudo pip install --default-timeout=1000 flask flask-restful  || die "Can't add xdrip cgm - error installing flask packages"
    sudo pip install --default-timeout=1000 -U flask-cors

    # xdrip CGM (xDripAPS), also gets installed when using xdrip-js
    if [[ ${CGM,,} =~ "xdrip" || ${CGM,,} =~ "xdrip-js" ]]; then
        echo xdrip or xdrip-js selected as CGM, so configuring xDripAPS
        sudo apt-get -y install sqlite3 || die "Can't add xdrip cgm - error installing sqlite3"
        git clone https://github.com/renegadeandy/xDripAPS.git $HOME/.xDripAPS
        mkdir -p $HOME/.xDripAPS_data
        do_openaps_import $HOME/src/oref0/lib/oref0-setup/xdrip-cgm.json
        touch /tmp/reboot-required
    fi

    # xdrip-js specific installation tasks (in addition to xdrip tasks)
    if [[ ${CGM,,} =~ "xdrip-js" ]]; then
        echo xdrip-js selected as CGM, so configuring xdrip-js
        git clone https://github.com/xdrip-js/Logger.git $HOME/src/Logger
        cd $HOME/src/Logger            
        sudo apt-get install -y bluez-tools
        sudo npm run global-install
        cgm-transmitter $DEXCOM_CGM_TX_ID
        touch /tmp/reboot-required
    fi

    # disable IPv6
    if ! grep -q 'net.ipv6.conf.all.disable_ipv6=1' /etc/sysctl.conf; then
        sudo echo 'net.ipv6.conf.all.disable_ipv6=1' >> /etc/sysctl.conf
    fi
    if ! grep -q 'net.ipv6.conf.default.disable_ipv6=1' /etc/sysctl.conf; then
        sudo echo 'net.ipv6.conf.default.disable_ipv6=1' >> /etc/sysctl.conf
    fi
    if ! grep -q 'net.ipv6.conf.lo.disable_ipv6=1' /etc/sysctl.conf; then
        sudo echo 'net.ipv6.conf.lo.disable_ipv6=1' >> /etc/sysctl.conf
    fi
    sudo sysctl -p

    # Install EdisonVoltage
    if is_edison; then
        echo "Checking if EdisonVoltage is already installed"
        if [ -d "$HOME/src/EdisonVoltage/" ]; then
            echo "EdisonVoltage already installed"
        else
            echo "Installing EdisonVoltage"
            cd $HOME/src && git clone -b master https://github.com/cjo20/EdisonVoltage.git || (cd EdisonVoltage && git checkout master && git pull)
            cd $HOME/src/EdisonVoltage
            make voltage
        fi
        # Add module needed for EdisonVoltage to work on jubilinux 0.2.0
        grep iio_basincove_gpadc /etc/modules-load.d/modules.conf || echo iio_basincove_gpadc >> /etc/modules-load.d/modules.conf
    fi
    #if [[ ${CGM,,} =~ "mdt" ]]; then # still need this for the old ns-loop for now
    #    cd $directory || die "Can't cd $directory"
    #    do_openaps_import $HOME/src/oref0/lib/oref0-setup/edisonbattery.json
    #fi
    # Install Pancreabble
    echo Checking for BT Pebble Mac
    if [[ ! -z "$BT_PEB" ]]; then
        sudo pip install --default-timeout=1000 libpebble2
        sudo pip install --default-timeout=1000 --user git+https://github.com/mddub/pancreabble.git
        oref0-bluetoothup
        sudo rfcomm bind hci0 $BT_PEB
        do_openaps_import $HOME/src/oref0/lib/oref0-setup/pancreabble.json
        sudo cp $HOME/src/oref0/lib/oref0-setup/pancreoptions.json $directory/pancreoptions.json
    fi

    # configure autotune if enabled
    if [[ $ENABLE =~ autotune ]]; then
        cd $directory || die "Can't cd $directory"
        do_openaps_import $HOME/src/oref0/lib/oref0-setup/autotune.json
        sudo locale-gen en_US.UTF-8
        sudo update-locale
    fi

    #Moved this out of the conditional, so that x12 models will work with smb loops
    sudo apt-get -y install bc ntpdate bash-completion || die "Couldn't install bc etc."
    # now required on all platforms for shared-node
    echo "Installing socat and ntp..."
    apt-get install -y socat ntp
    cd $directory || die "Can't cd $directory"
    do_openaps_import $HOME/src/oref0/lib/oref0-setup/supermicrobolus.json

    echo "Adding OpenAPS log shortcuts"
    # Make sure that .bash_profile exists first, then call script to add the log shortcuts
    touch "$HOME/.bash_profile"
    oref0-log-shortcuts --add-to-profile="$HOME/.bash_profile"

    # Append NIGHTSCOUT_HOST and API_SECRET to $HOME/.bash_profile so that openaps commands can be executed from the command line
    #echo Add NIGHTSCOUT_HOST and API_SECRET to $HOME/.bash_profile
    #sed --in-place '/.*NIGHTSCOUT_HOST.*/d' $HOME/.bash_profile
    #(cat $HOME/.bash_profile | grep -q "NIGHTSCOUT_HOST" || echo export NIGHTSCOUT_HOST="$NIGHTSCOUT_HOST" >> $HOME/.bash_profile)
    if [[ "${API_SECRET,,}" =~ "token=" ]]; then # install requirements for token based authentication
      API_HASHED_SECRET=${API_SECRET}
    else
      API_HASHED_SECRET=$(nightscout hash-api-secret $API_SECRET)
    fi
    # Check if API_SECRET exists, if so remove all lines containing API_SECRET and add the new API_SECRET to the end of the file
    #sed --in-place '/.*API_SECRET.*/d' $HOME/.bash_profile
    #(cat $HOME/.profile | grep -q "API_SECRET" || echo export API_SECRET="$API_HASHED_SECRET" >> $HOME/.profile)

    # With 0.5.0 release we switched from ~/.profile to ~/.bash_profile for API_SECRET and NIGHTSCOUT_HOST, because a shell will look
    # for ~/.bash_profile, ~/.bash_login, and ~/.profile, in that order, and reads and executes commands from
    # the first one that exists and is readable. Remove API_SECRET and NIGHTSCOUT_HOST lines from ~/.profile if they exist
    if [[ -f $HOME/.profile ]]; then
      sed --in-place '/.*API_SECRET.*/d' $HOME/.profile
      sed --in-place '/.*NIGHTSCOUT_HOST.*/d' $HOME/.profile
      sed --in-place '/.*MEDTRONIC_PUMP_ID.*/d' $HOME/.profile
      sed --in-place '/.*MEDTRONIC_FREQUENCY.*/d' $HOME/.profile
    fi

    # Delete old copies of variables before replacing them
    sed --in-place '/.*NIGHTSCOUT_HOST.*/d' $HOME/.bash_profile
    sed --in-place '/.*API_SECRET.*/d' $HOME/.bash_profile
    sed --in-place '/.*DEXCOM_CGM_RECV_ID*/d' $HOME/.bash_profile
    sed --in-place '/.*MEDTRONIC_PUMP_ID.*/d' $HOME/.bash_profile
    sed --in-place '/.*MEDTRONIC_FREQUENCY.*/d' $HOME/.bash_profile
    #sed --in-place '/.*DEXCOM_CGM_TX_ID*/d' $HOME/.bash_profile

    # Then append the variables
    echo NIGHTSCOUT_HOST="$NIGHTSCOUT_HOST" >> $HOME/.bash_profile
    echo "export NIGHTSCOUT_HOST" >> $HOME/.bash_profile
    echo API_SECRET="${API_HASHED_SECRET}" >> $HOME/.bash_profile
    echo "export API_SECRET" >> $HOME/.bash_profile
    echo DEXCOM_CGM_RECV_ID="$BLE_SERIAL" >> $HOME/.bash_profile
    echo "export DEXCOM_CGM_RECV_ID" >> $HOME/.bash_profile
    echo MEDTRONIC_PUMP_ID="$serial" >> $HOME/.bash_profile
    echo MEDTRONIC_FREQUENCY='`cat $HOME/myopenaps/monitor/medtronic_frequency.ini`' >> $HOME/.bash_profile
    
    #echo DEXCOM_CGM_TX_ID="$DEXCOM_CGM_TX_ID" >> $HOME/.bash_profile
    #echo "export DEXCOM_CGM_TX_ID" >> $HOME/.bash_profile

    #Turn on i2c, install pi-buttons, and openaps-menu for hardware that has a screen and buttons (so far, only Explorer HAT and Radiofruit Bonnet)
    if grep -qa "Explorer HAT" /proc/device-tree/hat/product &> /dev/null || [[ "$hardwaretype" =~ "explorer-hat" ]] || [[ "$hardwaretype" =~ "radiofruit" ]]; then
        echo "Looks like you have buttons and a screen!"
        echo "Enabling i2c device nodes..."
        if ! ( grep -q i2c-dev /etc/modules-load.d/i2c.conf && egrep "^dtparam=i2c1=on" /boot/config.txt ); then
            echo Enabling i2c for the first time: this will require a reboot after oref0-setup.
            touch /tmp/reboot-required
        fi
        sed -i.bak -e "s/#dtparam=i2c_arm=on/dtparam=i2c_arm=on/" /boot/config.txt
        egrep "^dtparam=i2c1=on" /boot/config.txt || echo "dtparam=i2c1=on,i2c1_baudrate=400000" >> /boot/config.txt
        echo "i2c-dev" > /etc/modules-load.d/i2c.conf
        echo "Installing pi-buttons..."
        systemctl stop pi-buttons
        cd $HOME/src && git clone https://github.com/bnielsen1965/pi-buttons.git
        echo "Make and install pi-buttons..."
        cd pi-buttons
        cd src && make && sudo make install && sudo make install_service
        # Radiofruit buttons are on different GPIOs than the Explorer HAT
        if  [[ "$hardwaretype" =~ "radiofruit" ]]; then
            sed -i 's/17,27/5,6/g' /etc/pi-buttons.conf
        fi
        systemctl enable pi-buttons && systemctl restart pi-buttons
        echo "Installing openaps-menu..."
        test "$directory" != "/$HOME/myopenaps" && (echo You are using a non-standard openaps directory. For the statusmenu to work correctly you need to set the openapsDir variable in index.js)
        cd $HOME/src && git clone https://github.com/openaps/openaps-menu.git || (cd openaps-menu && git checkout master && git pull)
        cd $HOME/src/openaps-menu && sudo npm install
        cp $HOME/src/openaps-menu/openaps-menu.service /etc/systemd/system/ && systemctl enable openaps-menu
    fi

    echo "Clearing retrieved apt packages to free space."
    apt-get autoclean && apt-get clean

    # Install Golang
    mkdir -p $HOME/go
    source $HOME/.bash_profile
    golangversion=1.12.5
    if go version | grep go${golangversion}.; then
        echo Go already installed
    else
        echo "Removing possible old go install..."
        rm -rf /usr/local/go/*
        echo "Installing Golang..."
        if uname -m | grep armv; then
            cd /tmp && wget -c https://storage.googleapis.com/golang/go${golangversion}.linux-armv6l.tar.gz && tar -C /usr/local -xzvf /tmp/go${golangversion}.linux-armv6l.tar.gz
        elif uname -m | grep i686; then
            cd /tmp && wget -c https://dl.google.com/go/go${golangversion}.linux-386.tar.gz && tar -C /usr/local -xzvf /tmp/go${golangversion}.linux-386.tar.gz
        fi
    fi
    if ! grep GOROOT $HOME/.bash_profile; then
        sed --in-place '/.*GOROOT*/d' $HOME/.bash_profile
        echo 'GOROOT=/usr/local/go' >> $HOME/.bash_profile
        echo 'export GOROOT' >> $HOME/.bash_profile
    fi
    if ! grep GOPATH $HOME/.bash_profile; then
        sed --in-place '/.*GOPATH*/d' $HOME/.bash_profile
        echo 'GOPATH=$HOME/go' >> $HOME/.bash_profile
        echo 'export GOPATH' >> $HOME/.bash_profile
        echo 'PATH=$PATH:/usr/local/go/bin:$GOROOT/bin:$GOPATH/bin' >> $HOME/.bash_profile
        sed --in-place '/.*export PATH*/d' $HOME/.bash_profile
        echo 'export PATH' >> $HOME/.bash_profile
    fi
    source $HOME/.bash_profile

    #Necessary to "bootstrap" Go commands...
    if [[ ${radio_locale,,} =~ "ww" ]]; then
      echo 868.4 > $directory/monitor/medtronic_frequency.ini
    else
      echo 916.55 > $directory/monitor/medtronic_frequency.ini
    fi

    # Build pump communication binaries
    # Exit if ttyport is not SPI. TODO: support UART-connected TI stick
    if [[ "$ttyport" =~ "spidev" ]]; then
        #Turn on SPI for all pi-based setups. Not needed on the Edison.
        if is_pi; then
          echo "Making sure SPI is enabled..."
          sed -i.bak -e "s/#dtparam=spi=on/dtparam=spi=on/" /boot/config.txt
        fi

        #Make sure radiotags are set properly for different hardware types
        #The only necessary one here at the moment is rfm69 (cc111x is the default in oref0-setup)
        case $hardwaretype in
          edison-explorer) radiotags="cc111x";;
          explorer-hat) radiotags="cc111x";;
          radiofruit) radiotags="rfm69";;
          arm-spi) radiotags="cc111x";;
          386-spi) radiotags="cc111x";;
        esac

        #Build Go binaries
        go get -u -v -tags "$radiotags" github.com/ecc1/medtronic/... || die "Couldn't go get medtronic"
        ln -sf $HOME/go/src/github.com/ecc1/medtronic/cmd/pumphistory/openaps.jq $directory/ || die "Couldn't softlink openaps.jq"
    else
        #TODO: write validate_ttyport and support non-SPI ports
        die "Unsupported ttyport. Exiting."
    fi

    if [[ ${CGM,,} =~ "g4-go" ]]; then
        if [ ! -d $HOME/go/bin ]; then mkdir -p $HOME/go/bin; fi
        echo "Compiling Go dexcom binaries ..."
        if is_edison; then
            go get -u -v -tags nofilter github.com/ecc1/dexcom/...
        else
            go get -u -v github.com/ecc1/dexcom/...
        fi
#        else
#            arch=arm
#            if egrep -i "edison" /etc/passwd &>/dev/null; then
#                arch=386
#            fi
#            downloadUrl=$(curl -s https://api.github.com/repos/ecc1/dexcom/releases/$ecc1dexcomversion | \
#            jq --raw-output '.assets[] | select(.name | contains("'$arch'")) | .browser_download_url')
#           echo "Downloading Go dexcom binaries from:" $downloadUrl
#            wget -qO- $downloadUrl | tar xJv -C $HOME/go/bin || die "Couldn't download and extract Go dexcom binaries"
#        fi
    fi

    copy_go_binaries
    move_mmtune

    # clear any extraneous input before prompting
    while(read -r -t 0.1); do true; done

    if prompt_yn "Schedule openaps in cron?" N; then

        echo Saving existing crontab to $HOME/crontab.txt:
        crontab -l | tee $HOME/crontab.old.txt
        if prompt_yn "Would you like to remove your existing crontab first?" N; then
            crontab -r
        fi

        # add crontab entries
        (crontab -l; crontab -l | grep -q "NIGHTSCOUT_HOST" || echo NIGHTSCOUT_HOST=$NIGHTSCOUT_HOST) | crontab -
        (crontab -l; crontab -l | grep -q "API_SECRET=" || echo API_SECRET=$API_HASHED_SECRET) | crontab -
        if validate_g4share_serial $BLE_SERIAL; then
            (crontab -l; crontab -l | grep -q "DEXCOM_CGM_RECV_ID=" || echo DEXCOM_CGM_RECV_ID=$BLE_SERIAL) | crontab -
        fi
        #if validate_g5transmitter_serial $DEXCOM_CGM_TX_ID; then
        #    (crontab -l; crontab -l | grep -q "DEXCOM_CGM_TX_ID=" || echo DEXCOM_CGM_TX_ID=$DEXCOM_CGM_TX_ID) | crontab -
        #fi
        # deduplicate to avoid multiple instances of $GOPATH in $PATH
        #echo $PATH
        dedupe_path;
        echo $PATH
        (crontab -l; crontab -l | grep -q "PATH=" || echo "PATH=$PATH" ) | crontab -

        add_to_crontab \
            "oref0-cron-every-minute" \
            '* * * * *' \
            "cd $directory && oref0-cron-every-minute"
        add_to_crontab \
            "oref0-cron-post-reboot" \
            '@reboot' \
            "cd $directory && oref0-cron-post-reboot"
        add_to_crontab \
            "oref0-cron-nightly" \
            "5 4 * * *" \
            "cd $directory && oref0-cron-nightly"
        add_to_crontab \
            "oref0-cron-every-15min" \
            "*/15 * * * *" \
            "cd $directory && oref0-cron-every-15min"
        if [[ ${CGM,,} =~ "xdrip-js" ]]; then
            add_to_crontab \
                "Logger" \
                "* * * * *" \
                "cd $HOME/src/Logger && ps aux | grep -v grep | grep -q Logger || /usr/local/bin/Logger >> /var/log/openaps/logger-loop.log 2>&1"
        fi
        crontab -l | tee $HOME/crontab.txt
    fi

    if [[ ${CGM,,} =~ "g4-go" ]]; then
        echo
        echo "To pair your G4 Share receiver, open its Settings, select Share, Forget Device (if previously paired), then turn sharing On"
    fi

fi # from 'read -p "Continue? y/[N] " -r' after interactive setup is complete

# Start cron back up in case the user doesn't decide to reboot
service cron start

if [ -e /tmp/reboot-required ]; then
  read -p "Reboot required.  Press enter to reboot or Ctrl-C to cancel"
  sudo reboot
fi
