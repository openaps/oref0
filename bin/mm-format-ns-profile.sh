#!/usr/bin/env bash

# Author: Ben West

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

SETTINGS=${1-monitor/settings.json}
CARBS=${2-monitor/carb-ratios.json}
BASALRATES=${3-monitor/active-basal-profile.json}
SENSITIVITIES=${4-monitor/insulin-sensitivities.json}
TARGETS=${5-monitor/bg-targets.json}
OUTPUT=${6-/dev/fd/1}
# DIA
# CARBRATIO
#TZ=${3-$(date +%z)}

usage "$@" <<EOT
Usage: $self pump-settings carb-ratios active-basal-profile insulin-sensitivities bg-targets

Format known pump data into Nightscout "profile".

Profile documents allow Nightscout to establish a common set of settings for
therapy, including the type of units used, the timezone, carb-ratios, active
basal profiles, insulin sensitivities, and BG targets.  This compiles the
separate pump reports into a single profile document for Nightscout.

Examples:
bewest@bewest-MacBookPro:~/Documents/openaps$ mm-format-ns-profile monitor/settings.json monitor/carb-ratios.json monitor/active-basal-profile.json monitor/insulin-sensitivities.json monitor/bg-targets.json

EOT

function dia ( ) {
  cat $1 | jq .insulin_action_curve
}

function fix-time-field ( ) {
  jq '[ .[] | .time = ( .time | split(":") | .[0:2] | join(":") ) ]'
}

function fix-schedule ( ) {
  field=$1
  jq '[ .[] | .time = .start | .value = ( .'$field' | tostring ) ]' \
    | fix-time-field
}

function carb-ratios ( ) {
  units=$(cat $1 | jq -r .units)
  if [[ $units = "grams" ]] ; then
    cat $1 | jq .schedule \
      | fix-schedule ratio
      # | json -e "this.time = this.start; this.value = this.ratio;"
  else
    echo "[]"
  fi

}

function add-carbs ( ) {
  jq '.carbratio = '"$(carb-ratios $1)"
}

function basal-rates ( ) {
  (
   test -n "$1" && cat $1 || echo "[ ]"
  ) | fix-schedule rate \
    | jq '[ .[] | if length > 0 then . else [] end ]'
    # | json -e "this.seconds = this.minutes * 60;"
}

function add-basals ( ) {
  jq '.basal = '"$(basal-rates $1)"
}

function sensitivities ( ) {
  (
   test -n "$1" && cat $1 || echo "{ }" | json
  )   \
    | jq '.
      | .sens = if .sensitivities and ((.sensitivities | length) > 0) then .sensitivities else [] end
      | .sens'  \
    | fix-schedule sensitivity
}

function add-isf ( ) {
  #json -e "this.sens =
  # sensitivities $1
  jq '.sens = '"$(sensitivities $1)"
}

function targets ( ) {
  category="$2"
  test -z "$category" && category=$1 && shift 
  (
   test -n "${1}${2}" && cat $1 || echo "{ }"
  )   \
    | target-category $category

}

function target-category ( ) {
  category="$1"
  name="target_$category"
  jq 'if .targets | length > 0 then .targets else [] end' | \
  jq '{ "'$name'": [ .[] | { "value": ( .'$category' | tostring ), "time": .start } ] }' | \
  jq .$name | fix-time-field
}

function add-targets ( ) {
  jq '.target_low = '"$(targets $1 low)"'
    | .target_high = '"$(targets $1 high)"'
    | .units = '$(bgunits $1)
}

function bgunits ( ) {
  cat $1 | jq .units
}

function fix-dates ( ) {
  # really want to know last changed date
  startDate=$(date --date "1 minute ago" --iso-8601=minutes)
  created_at=$(date --iso-8601=minutes)
  jq '.created_at = "'$created_at'"
    | .startDate = "'$startDate'"'
}

function stub ( ) {
  zone=$(cat /etc/timezone | nonl)
  dt=$(date --rfc-3339=ns | tr ' ' 'T')
  DIA=$(dia $SETTINGS)
  cat <<EOF | jq .
  {
    "dia" : "$DIA"
  , "carbratio": [ ]
  , "carbs_hr": "30"
  , "delay": "20"
  , "sens": [ ]
  , "startDate": "$dt"
  , "timezone": "$zone"
  , "basal": [ ]
  , "target_low": [ ]
  , "target_high": [ ]
  , "created_at": "$dt"
  , "units": ""
  }
EOF
}

stub $SETTINGS | fix-dates  \
  | add-carbs $CARBS \
  | add-basals $BASALRATES \
  | add-isf $SENSITIVITIES \
  | add-targets $TARGETS \
  | jq . > $OUTPUT


