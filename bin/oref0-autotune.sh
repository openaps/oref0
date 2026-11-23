#!/usr/bin/env bash

# This script sets up an easy test environment for autotune, allowing the user to vary parameters 
# like start/end date.
# 
# Required Inputs: 
#   DIR, (--dir=<OpenAPS Directory>)
#   NIGHTSCOUT_HOST, (--ns-host=<NIGHTSCOUT SITE URL)
#   START_DATE, (--start-date=<YYYY-MM-DD>)
# Optional Inputs:
#   END_DATE, (--end-date=<YYYY-MM-DD>) 
#     if no end date supplied, assume we want a months worth or until day before current day
#   EXPORT_EXCEL (--xlsx=<filenameofexcel>)
#     export to excel. Disabled by default
#   TERMINAL_LOGGING (--log <true/false(true)>
#     logs terminal output to autotune.<date stamp>.log in the autotune directory, default to true
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

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

die() {
    if [[ -z "$API_SECRET" ]]; then
        echo "Warning: API_SECRET is not set when calling oref0-autotune.sh"
        echo "(this is only a problem if you have locked down read-only access to your NS)."
    fi

    echo "$@"
    exit 1
}

# defaults
CURL_FLAGS="--compressed"
DIR=""
NIGHTSCOUT_HOST=""
START_DATE=""
END_DATE=""
START_DAYS_AGO=1  # Default to yesterday if not otherwise specified
END_DAYS_AGO=1  # Default to yesterday if not otherwise specified
EXPORT_EXCEL="" # Default is to not export to Microsoft Excel
TERMINAL_LOGGING=true
CATEGORIZE_UAM_AS_BASAL=false
TUNE_INSULIN_CURVE=false
RECOMMENDS_REPORT=true
UNKNOWN_OPTION=""

if [ -n "${API_SECRET_READ}" ]; then 
   echo "WARNING: API_SECRET_READ is deprecated starting with oref 0.6.x. The Nightscout authentication information is now used from the API_SECRET environment variable"
fi

# If we are running OS X or BSD, we need to use a different version
# of the 'date' command; the built-in 'date' is BSD, which
# has fewer options than the linux version.  So the user
# needs to install coreutils, which gives the GNU 'date'
# command as 'gdate':

shopt -s expand_aliases

if [[ `uname` == 'Darwin' || `uname` == 'FreeBSD' || `uname` == 'OpenBSD' ]] ; then
    alias date='gdate'
fi

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
    -x=*|--xlsx=*)
    EXPORT_EXCEL="${i#*=}"
    shift # past argument=value
    ;;
    -l=*|--log=*)
    TERMINAL_LOGGING="${i#*=}"
    shift
    ;;
    -c=*|--categorize-uam-as-basal=*)
    CATEGORIZE_UAM_AS_BASAL="${i#*=}"
    shift
    ;;
    -i=*|--tune-insulin-curve=*)
    TUNE_INSULIN_CURVE="${i#*=}"
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
NIGHTSCOUT_HOST="${NIGHTSCOUT_HOST%/}"
export NIGHTSCOUT_HOST

if [[ -z "$DIR" || -z "$NIGHTSCOUT_HOST" ]]; then
    echo "Usage: oref0-autotune <--dir=myopenaps_directory> <--ns-host=https://mynightscout.azurewebsites.net> [--start-days-ago=number_of_days] [--end-days-ago=number_of_days] [--start-date=YYYY-MM-DD] [--end-date=YYYY-MM-DD] [--xlsx=autotune.xlsx] [--log=(true)|false] [--categorize-uam-as-basal=true|(false)] [--tune-insulin-curve=true|(false) ]"
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
  echo "Running oref0-autotune --dir=$DIR --start-date=$START_DATE --end-date=$END_DATE --categorize-uam-as-basal=$CATEGORIZE_UAM_AS_BASAL"
else
  echo "Unknown options. Exiting"
  exit 1
fi

if [[ -z "$START_DATE" || -z "$END_DATE" || "$START_DATE" > "$END_DATE" ]]; then
    die "Invalid autotune date range"
fi

# Build date list for autotune iteration
date_list=()
date=$START_DATE;
while :
do
  date_list+=( "$date" )
  if [ $date != "$END_DATE" ]; then
    date="$(date --date="$date + 1 days" +%Y-%m-%d)" || die "Invalid autotune date";
  else
    break
  fi
done

# Validate the whole run before touching existing profiles or archives.
staged_inputs=$(mktemp -d "${TMPDIR:-/tmp}/oref0-autotune.XXXXXXXX") || die "Cannot stage autotune inputs"
trap 'rm -rf -- "$staged_inputs"' EXIT

validate_inputs() {
    node - "$0" "$@" <<'NODE'
const fs = require('fs');
const path = require('path');
const args = process.argv.slice(2);
const script = fs.realpathSync(args.shift());
const hasInsulinHistory = require(path.resolve(path.dirname(script), '../lib/autotune-prep/insulin-history'));
const file = args[0];
const kind = args[1];
const start = Number(args[2]);
const end = Number(args[3]);
const dayStart = Number(args[4]);
const dayEnd = Number(args[5]);
const maxRows = Number(args[6]);

function reject(reason) {
    console.error('Invalid autotune ' + kind + ' input: ' + reason);
    process.exit(1);
}

let rows;
try {
    rows = JSON.parse(fs.readFileSync(file, 'utf8'));
} catch (_) {
    reject('invalid JSON');
}
if (!Array.isArray(rows) || rows.length === 0 || rows.length >= maxRows) {
    reject('missing, empty, or potentially truncated response');
}

let usableGlucose = false;
for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) reject('invalid row');
    const time = kind === 'glucose' ? row.date : Date.parse(row.created_at);
    if (!Number.isFinite(time) || time < start || time > end) reject('invalid or out-of-window timestamp');
    if (kind === 'glucose') {
        const glucose = row.glucose || row.sgv;
        // The categorizer ignores low CGM error codes. A few such readings
        // must not invalidate an otherwise usable day.
        if (['number', 'string'].includes(typeof glucose) && Number.isFinite(Number(glucose)) && Number(glucose) >= 39) {
            usableGlucose = true;
        }
    } else {
        const amounts = [row.insulin, row.carbs];
        if (amounts.some(value => value != null && value !== '' && !Number.isFinite(Number(value)))) {
            reject('invalid carb or insulin value');
        }
    }
}
if (kind === 'glucose' && !usableGlucose) reject('no usable glucose data');
if (kind === 'treatment' && !hasInsulinHistory(rows, dayStart, dayEnd)) reject('no usable insulin history in the tuning day');
NODE
}

echo "Downloading and validating Nightscout glucose and treatments before autotune"
for i in "${date_list[@]}"
do
    glucose_start=$(date --date="$i +4 hours" +%s) || die "Invalid glucose window start"
    glucose_end=$(date --date="$i +28 hours" +%s) || die "Invalid glucose window end"
    treatment_start=$(date --date="$i -18 hours" +%s) || die "Invalid treatment window start"
    treatment_end=$(date --date="$i +42 hours" +%s) || die "Invalid treatment window end"
    glucose_query="find%5Bdate%5D%5B%24gte%5D=${glucose_start}000&find%5Bdate%5D%5B%24lte%5D=${glucose_end}000&count=1500"
    # UTC produces a consistently encoded and comparable ISO treatment query.
    treatment_start_iso=$(date --utc --date="@$treatment_start" +%Y-%m-%dT%H:%M:%S.000Z)
    treatment_end_iso=$(date --utc --date="@$treatment_end" +%Y-%m-%dT%H:%M:%S.000Z)
    treatment_query="find%5Bcreated_at%5D%5B%24gte%5D=$treatment_start_iso&find%5Bcreated_at%5D%5B%24lte%5D=$treatment_end_iso&count=4096"

    glucose_file="$staged_inputs/ns-entries.$i.json"
    treatment_file="$staged_inputs/ns-treatments.$i.json"
    NIGHTSCOUT_STRICT_READ=1 ns-get host "$NIGHTSCOUT_HOST" entries/sgv.json "$glucose_query" > "$glucose_file" \
        || die "Nightscout glucose download failed for $i"
    NIGHTSCOUT_STRICT_READ=1 ns-get host "$NIGHTSCOUT_HOST" treatments.json "$treatment_query" > "$treatment_file" \
        || die "Nightscout treatment download failed for $i"
    validate_inputs "$glucose_file" glucose "${glucose_start}000" "${glucose_end}000" "${glucose_start}000" "${glucose_end}000" 1500 \
        || die "Autotune skipped for $i: glucose inputs failed validation"
    validate_inputs "$treatment_file" treatment "${treatment_start}000" "${treatment_end}000" "${glucose_start}000" "${glucose_end}000" 4096 \
        || die "Autotune skipped for $i: treatment inputs failed validation"
done

# Get profile for testing copied to home directory.
cd $directory && mkdir -p autotune
cp settings/pumpprofile.json autotune/profile.pump.json || die "Cannot copy settings/pumpprofile.json"
# This allows manual users to be able to run autotune by simply creating a settings/pumpprofile.json file.
if [[ `uname` == 'Darwin' || `uname` == 'FreeBSD' || `uname` == 'OpenBSD' ]] ; then
    cp settings/pumpprofile.json settings/profile.json || die "Cannot copy settings/pumpprofile.json"
else
    cp -up settings/pumpprofile.json settings/profile.json || die "Cannot copy settings/pumpprofile.json"
fi
# If a previous valid settings/autotune.json exists, use that; otherwise start from settings/profile.json
cp settings/autotune.json autotune/profile.json && cat autotune/profile.json | jq . | grep -q start || cp autotune/profile.pump.json autotune/profile.json
cd autotune

# Turn on stderr logging, if enabled (default to true)
if [[ $TERMINAL_LOGGING = "true" ]]; then
  # send stderr to a file as well as the terminal
  exec &> >(tee -a autotune.$(date +%Y-%m-%d-%H%M%S).log)
fi

echo "Compressing old json and log files to save space..."
gzip -f ns-*.json
gzip -f autotune*.json
# only gzip autotune log files more than 2 days old
find autotune.*.log -mtime +2 | while read file; do gzip -f $file; done
echo "Autotune disk usage:"
du -h .
echo "Overall disk used/avail:"
df -h .

for i in "${date_list[@]}"
do
    mv -- "$staged_inputs/ns-entries.$i.json" "$staged_inputs/ns-treatments.$i.json" . \
        || die "Cannot store verified inputs for $i"

    # Do iterative runs over date range, save autotune.json (prepped data) and input/output profile.json
    cp profile.json profile.$i.json
    # Autotune Prep (required args, <pumphistory.json> <profile.json> <glucose.json>), output prepped glucose 
    # data or <autotune/glucose.json> below
    if [[ $CATEGORIZE_UAM_AS_BASAL = "true" ]]; then
        CATEGORIZE_UAM_AS_BASAL_OPT="--categorize_uam_as_basal"
    else
        CATEGORIZE_UAM_AS_BASAL_OPT=
    fi

    if [[ $TUNE_INSULIN_CURVE = "true" ]]; then
        TUNE_INSULIN_CURVE_OPT="--tune-insulin-curve"
    else
        TUNE_INSULIN_CURVE_OPT=
    fi

    echo "oref0-autotune-prep $CATEGORIZE_UAM_AS_BASAL_OPT $TUNE_INSULIN_CURVE_OPT ns-treatments.$i.json profile.json ns-entries.$i.json profile.pump.json > autotune.$i.json"
    oref0-autotune-prep $CATEGORIZE_UAM_AS_BASAL_OPT $TUNE_INSULIN_CURVE_OPT ns-treatments.$i.json profile.json ns-entries.$i.json profile.pump.json > autotune.$i.json \
        || die "Could not run oref0-autotune-prep ns-treatments.$i.json profile.json ns-entries.$i.json"
    
    # Autotune  (required args, <autotune/glucose.json> <autotune/autotune.json> <settings/profile.json>), 
    # output autotuned profile or what will be used as <autotune/autotune.json> in the next iteration
    echo "oref0-autotune-core autotune.$i.json profile.json profile.pump.json > newprofile.$i.json"
    if ! oref0-autotune-core autotune.$i.json profile.json profile.pump.json > newprofile.$i.json; then
        if cat profile.json | jq --exit-status .carb_ratio==null; then
            echo "ERROR: profile.json contains null carb_ratio: using profile.pump.json"
            cp profile.pump.json profile.json
            exit
        else
            die "Could not run oref0-autotune-core autotune.$i.json profile.json profile.pump.json. Make sure Nightscout contains BG-values for the selected date range, Autotune(Web) does not work without BG-values. See documentation on the how-to check http://nightscout.github.io/nightscout/reports/#day-to-day ."
        fi
    else
        # Copy tuned profile produced by autotune to profile.json for use with next day of data
        if cat newprofile.$i.json | jq . | grep -q start; then
            cp newprofile.$i.json profile.json
        else
            jq -c newprofile.$i.json
            die "newprofile.$i.json invalid"
        fi
    fi


    if ! [[ -z "$EXPORT_EXCEL" ]]; then
        echo Exporting to $EXPORT_EXCEL
        oref0-autotune-export-to-xlsx --dir $DIR --output $EXPORT_EXCEL
    fi

    # Create Summary Report of Autotune Recommendations and display in the terminal
    if [[ $RECOMMENDS_REPORT == "true" ]]; then
        # Set the report file name, so we can let the user know where it is and cat
        # it to the screen
        report_file=$directory/autotune/autotune_recommendations.log

        echo
        echo "Autotune pump profile recommendations:"
        echo "---------------------------------------------------------"

        # Let the user know where the Autotune Recommendations are logged
        echo "Recommendations Log File: $report_file"
        echo

        # Run the Autotune Recommends Report
        oref0-autotune-recommends-report $directory

        # Go ahead and echo autotune_recommendations.log to the terminal, minus blank lines
        cat $report_file | egrep -v "\| *\| *$"
    fi

done # End Date Range Iteration
