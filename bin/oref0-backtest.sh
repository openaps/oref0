#!/bin/bash

# usage: $0

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

function stats {
    cat glucose.json | jq .[].sgv | awk -f ~/src/oref0/bin/glucose-stats.awk
}

# defaults
DIR="/tmp/oref0-simulator"
NIGHTSCOUT_HOST=""
START_DATE=""
END_DATE=""
START_DAYS_AGO=1  # Default to yesterday if not otherwise specified
END_DAYS_AGO=1  # Default to yesterday if not otherwise specified
EXPORT_EXCEL="" # Default is to not export to Microsoft Excel
TERMINAL_LOGGING=true
UNKNOWN_OPTION=""


# handle input arguments
for i in "$@"
do
case $i in
    -d=*|--dir=*)
    DIR="${i#*=}"
    # ~/ paths have to be expanded manually
    DIR="${DIR/#\~/$HOME}"
    # If DIR is a symlink, get actual path: 
    if [[ -L $DIR ]] ; then
        directory="$(readlink $DIR)"
    else
        directory="$DIR"
    fi
    shift # past argument=value
    ;;
    -n=*|--ns-host=*)
    NIGHTSCOUT_HOST="${i#*=}"
    shift # past argument=value
    ;;
    -s=*|--start-date=*)
    START_DATE="${i#*=}"
    START_DATE=`date --date="$START_DATE" +%Y-%m-%d`
    shift # past argument=value
    ;;
    -e=*|--end-date=*)
    END_DATE="${i#*=}"
    END_DATE=`date --date="$END_DATE" +%Y-%m-%d`
    shift # past argument=value
    ;;
    -t=*|--start-days-ago=*)
    START_DAYS_AGO="${i#*=}"
    shift # past argument=value
    ;;
    -d=*|--end-days-ago=*)
    END_DAYS_AGO="${i#*=}"
    shift # past argument=value
    ;;
    -l=*|--log=*)
    TERMINAL_LOGGING="${i#*=}"
    shift
    ;;
    *)
    # unknown option
    echo "Option ${i#*=} unknown"
    UNKNOWN_OPTION="yes"
    ;;
esac
done

# remove any trailing / from NIGHTSCOUT_HOST
NIGHTSCOUT_HOST=$(echo $NIGHTSCOUT_HOST | sed 's/\/$//g')

# TODO: add support for backtesting from autotune.*.log files specified on the command-line via glob, as an alternative to NS
if [[ -z "$NIGHTSCOUT_HOST" ]]; then
    echo "Usage: $0 [--dir=/tmp/oref0-simulator] --ns-host=https://mynightscout.herokuapp.com [--start-days-ago=number_of_days] [--end-days-ago=number_of_days] [--start-date=YYYY-MM-DD] [--end-date=YYYY-MM-DD] [--log=(true)|false] ]"
exit 1
fi
if [[ -z "$START_DATE" ]]; then
    # Default start date of yesterday
    START_DATE=`date --date="$START_DAYS_AGO days ago" +%Y-%m-%d`
fi
if [[ -z "$END_DATE" ]]; then
    # Default end-date as this morning at midnight in order to not get partial day samples for now
    # (ISF/CSF adjustments are still single values across each day)
    END_DATE=`date --date="$END_DAYS_AGO days ago" +%Y-%m-%d`
fi

if [[ -z "$UNKNOWN_OPTION" ]] ; then # everything is ok
  echo "Running oref0-backtest --dir=$DIR --ns-host=$NIGHTSCOUT_HOST --start-date=$START_DATE --end-date=$END_DATE"
else
  echo "Unknown options. Exiting"
  exit 1
fi


# TODO: support $DIR in oref0-simulator
oref0-simulator init $DIR
cd $DIR

# download profile.json from Nightscout profile.json endpoint and copy over to pumpprofile.json for autotuning
~/src/oref0/bin/get_profile.py --nightscout $NIGHTSCOUT_HOST display --format openaps 2>/dev/null > profile.json.new
if jq -e .dia profile.json.new; then
    jq -s '.[0] * .[1]' profile.json profile.json.new > profile.json.new.merged
    if jq -e .dia profile.json.new.merged; then
        mv profile.json.new.merged profile.json
    else
        echo Bad profile.json.new.merged
    fi
else
    echo Bad profile.json.new from get_profile.py
fi
cp profile.json pumpprofile.json

# download preferences.json from Nightscout devicestatus.json endpoint and overwrite profile.json with it
for i in $(seq 0 10); do
    curl $NIGHTSCOUT_HOST/api/v1/devicestatus.json | jq .[$i].preferences > preferences.json.new
    if jq -e .max_iob preferences.json.new; then
        mv preferences.json.new preferences.json
        jq -s '.[0] * .[1]' profile.json preferences.json > profile.json.new
        if jq -e .max_iob profile.json.new; then
            mv profile.json.new profile.json
            echo Successfully merged preferences.json into profile.json
            break
        else
            echo Bad profile.json.new from preferences.json merge attempt $1
        fi
    fi
done

# TODO: download historical glucose data from Nightscout entries.json for the day leading up to $START_DATE
echo oref0-autotune --dir=$DIR --ns-host=$NIGHTSCOUT_HOST --start-date=$START_DATE --end-date=$END_DATE 
oref0-autotune --dir=$DIR --ns-host=$NIGHTSCOUT_HOST --start-date=$START_DATE --end-date=$END_DATE | grep "dev: " | awk '{print $13 "," $20}' | while IFS=',' read dev carbs; do
    ~/src/oref0/bin/oref0-simulator.sh $dev 0 $carbs
done
cp autotune/profile.json settings/autotune.json

stats

