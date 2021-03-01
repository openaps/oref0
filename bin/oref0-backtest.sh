#!/bin/bash

# usage: $0

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

function stats {
    echo Simulated:
    cat all-glucose.json | jq '.[] | select (.device=="fakecgm") | .sgv' | awk -f ~/src/oref0/bin/glucose-stats.awk
    echo Actual:
    cat ns-entries.json | jq .[].sgv | awk -f ~/src/oref0/bin/glucose-stats.awk
}

# defaults
DIR="/tmp/oref0-simulator.$(mydate +%s)"
NIGHTSCOUT_HOST=""
START_DATE=""
END_DATE=""
START_DAYS_AGO=1  # Default to yesterday if not otherwise specified
END_DAYS_AGO=1  # Default to yesterday if not otherwise specified
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
    START_DATE=`mydate --date="$START_DATE" +%Y-%m-%d`
    shift # past argument=value
    ;;
    -e=*|--end-date=*)
    END_DATE="${i#*=}"
    END_DATE=`mydate --date="$END_DATE" +%Y-%m-%d`
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
    -p=*|--preferences=*)
    PREF="${i#*=}"
    # ~/ paths have to be expanded manually
    PREF="${PREF/#\~/$HOME}"
    # If PREF is a symlink, get actual path:
    if [[ -L $PREF ]] ; then
        preferences="$(readlink $PREF)"
    else
        preferences="$PREF"
    fi
    shift
    ;;
    -r=*|--profile=*)
    PROF="${i#*=}"
    # ~/ paths have to be expanded manually
    PROF="${PROF/#\~/$HOME}"
    # If PROF is a symlink, get actual path:
    if [[ -L $PROF ]] ; then
        profile="$(readlink $PROF)"
    else
        profile="$PROF"
    fi
    shift
    ;;
    -a=*|--autosens-override=*)
    AS_OVER="${i#*=}"
    # ~/ paths have to be expanded manually
    AS_OVER="${AS_OVER/#\~/$HOME}"
    # If AS_OVER is a symlink, get actual path:
    if [[ -L $AS_OVER ]] ; then
        as_override="$(readlink $AS_OVER)"
    else
        as_override="$AS_OVER"
    fi
    shift
    ;;
    *)
    # unknown option
    OPT=${i#*=}
    # ~/ paths have to be expanded manually
    OPT="${OPT/#\~/$HOME}"
    # If OPT is a symlink, get actual path:
    if [[ -L $OPT ]] ; then
        autotunelog="$(readlink $OPT)"
    else
        autotunelog="$OPT"
    fi
    if ls $autotunelog; then
        shift
    else
        echo "Option $OPT unknown"
        UNKNOWN_OPTION="yes"
    fi
    ;;
esac
done

# remove any trailing / from NIGHTSCOUT_HOST
NIGHTSCOUT_HOST=$(echo $NIGHTSCOUT_HOST | sed 's/\/$//g')

if [[ -z "$NIGHTSCOUT_HOST" ]] && [[ -z "$autotunelog" ]]; then
    # nightscout mode: download data from Nightscout
    echo "Usage: NS mode: $0 [--dir=/tmp/oref0-simulator] --ns-host=https://mynightscout.herokuapp.com [--start-days-ago=number_of_days] [--end-days-ago=number_of_days] [--start-date=YYYY-MM-DD] [--end-date=YYYY-MM-DD] [--preferences=/path/to/preferences.json] [--autosens-override=/path/to/autosens-override.json]"
    # file mode: for backtesting from autotune.*.log files specified on the command-line via glob, as an alternative to NS
    echo "Usage: file mode: $0 [--dir=/tmp/oref0-simulator] /path/to/autotune*.log [--profile=/path/to/profile.json] [--preferences=/path/to/preferences.json] [--autosens-override=/path/to/autosens-override.json]"
    exit 1
fi
if [[ -z "$START_DATE" ]]; then
    # Default start date of yesterday
    START_DATE=`mydate --date="$START_DAYS_AGO days ago" +%Y-%m-%d`
fi
if [[ -z "$END_DATE" ]]; then
    # Default end-date as this morning at midnight in order to not get partial day samples for now
    # (ISF/CSF adjustments are still single values across each day)
    END_DATE=`mydate --date="$END_DAYS_AGO days ago" +%Y-%m-%d`
fi

if [[ -z "$UNKNOWN_OPTION" ]] ; then # everything is ok
    if [[ -z "$NIGHTSCOUT_HOST" ]]; then
        echo "Running oref0-backtest --dir=$DIR $autotunelog" | tee -a $DIR/commands.log
    else
        echo "Running oref0-backtest --dir=$DIR --ns-host=$NIGHTSCOUT_HOST --start-date=$START_DATE --end-date=$END_DATE" | tee -a $DIR/commands.log
    fi
else
    echo "Unknown options. Exiting"
    exit 1
fi

oref0-simulator init $DIR
cd $DIR
mkdir -p autotune

# nightscout mode: download data from Nightscout
if ! [[ -z "$NIGHTSCOUT_HOST" ]]; then
    # download profile.json from Nightscout profile.json endpoint, and also copy over to pumpprofile.json
    ~/src/oref0/bin/get_profile.py --nightscout $NIGHTSCOUT_HOST display --format openaps 2>/dev/null > profile.json.new
    ls -la profile.json.new
    grep bg profile.json.new
    if jq -e .dia profile.json.new; then
        jq -rs 'reduce .[] as $item ({}; . * $item)' profile.json profile.json.new | jq '.sens = .isfProfile.sensitivities[0].sensitivity' > profile.json.new.merged
        ls -la profile.json.new.merged
        if jq -e .dia profile.json.new.merged; then
            mv profile.json.new.merged profile.json
        else
            echo Bad profile.json.new.merged
        fi
    else
        echo Bad profile.json.new from get_profile.py
    fi
    grep bg profile.json

    # download preferences.json from Nightscout devicestatus.json endpoint and overwrite profile.json with it
    for i in $(seq 0 10); do
        curl $NIGHTSCOUT_HOST/api/v1/devicestatus.json | jq .[$i].preferences > preferences.json.new
        if jq -e .max_iob preferences.json.new; then
            mv preferences.json.new preferences.json
            jq -s '.[0] + .[1]' profile.json preferences.json > profile.json.new
            if jq -e .max_iob profile.json.new; then
                mv profile.json.new profile.json
                echo Successfully merged preferences.json into profile.json
                break
            else
                echo Bad profile.json.new from preferences.json merge attempt $1
            fi
        fi
    done
fi

# read a --profile file (overriding NS profile if it exists)
if [[ -e $profile ]]; then
    jq -s '.[0] + .[1]' profile.json $profile > profile.json.new
    if jq -e .max_iob profile.json.new; then
        mv profile.json.new profile.json
        echo Successfully merged $profile into profile.json
    else
        echo Unable to merge $profile into profile.json
    fi
fi

# read a --preferences file to override the one from nightscout (for testing impact of different preferences)
if [[ -e $preferences ]]; then
    cat $preferences
    jq -s '.[0] + .[1]' profile.json $preferences > profile.json.new
    if jq -e .max_iob profile.json.new; then
        mv profile.json.new profile.json
        echo Successfully merged $preferences into profile.json
        grep target_bg profile.json
    else
        echo Unable to merge $preferences into profile.json
    fi
fi

cp profile.json settings/
cp profile.json pumpprofile.json
cp pumpprofile.json settings/

if [[ -e $as_override ]]; then
    echo Overriding autosens with:
    cat $as_override
    cp $as_override autosens-override.json
fi

if ! [[ -z "$NIGHTSCOUT_HOST" ]]; then
    # download historical glucose data from Nightscout entries.json for the day leading up to $START_DATE at 4am
    query="find%5Bdate%5D%5B%24gte%5D=$(to_epochtime "$START_DATE -24 hours" |nonl; echo 000)&find%5Bdate%5D%5B%24lte%5D=$(to_epochtime "$START_DATE +4 hours" |nonl; echo 000)&count=1500"
    echo Query: $NIGHTSCOUT_HOST entries/sgv.json $query
    ns-get host $NIGHTSCOUT_HOST entries/sgv.json $query > ns-entries.json || die "Couldn't download ns-entries.json"
    ls -la ns-entries.json || die "No ns-entries.json downloaded"
    if jq -e .[0].sgv ns-entries.json; then
        mv ns-entries.json glucose.json
        cp glucose.json all-glucose.json
        cat glucose.json | jq .[0].dateString > clock.json
    fi
    # download historical treatments data from Nightscout treatments.json for the day leading up to $START_DATE at 4am
    query="find%5Bcreated_at%5D%5B%24gte%5D=`mydate --date="$START_DATE -24 hours" -Iminutes`&find%5Bcreated_at%5D%5B%24lte%5D=`mydate --date="$START_DATE +4 hours" -Iminutes`"
    echo Query: $NIGHTSCOUT_HOST treatments.json $query
    ns-get host $NIGHTSCOUT_HOST treatments.json $query > ns-treatments.json || die "Couldn't download ns-treatments.json"
    ls -la ns-treatments.json || die "No ns-treatments.json downloaded"
    if jq -e .[0].created_at ns-treatments.json; then
        mv ns-treatments.json pumphistory.json
    fi

    # download actual glucose data from Nightscout entries.json for the simulated time period
    query="find%5Bdate%5D%5B%24gte%5D=$(to_epochtime "$START_DATE +4 hours" |nonl; echo 000)&find%5Bdate%5D%5B%24lte%5D=$(to_epochtime "$END_DATE +28 hours" |nonl; echo 000)&count=9999999"
    echo Query: $NIGHTSCOUT_HOST entries/sgv.json $query
    ns-get host $NIGHTSCOUT_HOST entries/sgv.json $query > ns-entries.json || die "Couldn't download ns-entries.json"
    ls -la ns-entries.json || die "No ns-entries.json downloaded"
fi

# file mode: run simulator from deviations from an autotune log file
if ! [[ -z "$autotunelog" ]]; then
    echo cat $autotunelog | tee -a $DIR/commands.log
    cat $autotunelog | grep "dev: " | awk '{print $13 "," $20}' | while IFS=',' read dev carbs; do
        ~/src/oref0/bin/oref0-simulator.sh $dev 0 $carbs $DIR
    done
    exit 0
fi

if ! [[ -z "$NIGHTSCOUT_HOST" ]]; then
    # sleep for 10s to allow multiple parallel runs to start up before loading up the CPUs
    sleep 10
    echo oref0-autotune --dir=$DIR --ns-host=$NIGHTSCOUT_HOST --start-date=$START_DATE --end-date=$END_DATE | tee -a $DIR/commands.log
    oref0-autotune --dir=$DIR --ns-host=$NIGHTSCOUT_HOST --start-date=$START_DATE --end-date=$END_DATE | grep "dev: " | awk '{print $13 "," $20}' | while IFS=',' read dev carbs; do
        ~/src/oref0/bin/oref0-simulator.sh $dev 0 $carbs $DIR
    done
    exit 0
fi

echo Error: neither autotunelog nor NIGHTSCOUT_HOST set
exit 1
