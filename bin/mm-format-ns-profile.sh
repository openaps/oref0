#!/bin/bash

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
  cat $1 | json insulin_action_curve
}

function fix-time-field ( ) {
  json -e "this.time = this.time.split(':').slice(0, 2).join(':')"
}

function fix-schedule ( ) {
  field=$1
  json -e "this.time = this.start; this.value = this.$field.toString( );" \
    | fix-time-field
}

function carb-ratios ( ) {
  units=$(cat $1 | json units)
  if [[ $units = "grams" ]] ; then
    cat $1 | json schedule \
      | fix-schedule ratio
      # | json -e "this.time = this.start; this.value = this.ratio;"
  else
    echo "[ ]" | json
  fi

}

function add-carbs ( ) {
  json -e "this.carbratio = $(carb-ratios $1 )"
}

function basal-rates ( ) {
  (
   test -n "$1" && cat $1 || echo "[ ]"
  ) | json  \
    | fix-schedule rate \
    | json -A -e "this.length > 0 ? this : [ ];"
    # | json -e "this.seconds = this.minutes * 60;"
}

function add-basals ( ) {
  json -e "this.basal = $(basal-rates $1 )"
}

function sensitivities ( ) {
  (
   test -n "$1" && cat $1 || echo "{ }" | json
  )   \
    | json -e "this.sens = (this.sensitivities && this.sensitivities.length > 0) ? this.sensitivities : [ ];" \
    | json  sens  \
    | fix-schedule sensitivity
}

function add-isf ( ) {
  #json -e "this.sens =
  # sensitivities $1
  json -e "this.sens = $(sensitivities $1 )"
}

function targets ( ) {
  category="$2"
  test -z "$category" && category=$1 && shift 
  (
   test -n "${1}${2}" && cat $1 || echo "{ }" | json
  )   \
    | target-category $category

}

function target-category ( ) {
  category="$1"
  name="target_$category"
  json -e "this.$name = (this.targets && this.targets.length > 0) ? this.targets : [ ];" \
   | json -e "this.$name = this.$name.map(function (elem) { if (elem.$category) { return {value: elem.$category.toString( ), time: elem.start }; } })" \
   json $name | fix-time-field
}

function add-targets ( ) {
  json -e "this.target_low = $(targets $1 low)" \
    | json -e "this.target_high = $(targets $1 high)" \
    | json -e "this.units = '$(bgunits $1)'"

}

function bgunits ( ) {
  cat $1 | json units
}

function fix-dates ( ) {
  # really want to know last changed date
  startDate=$(date --date "1 minute ago" --iso-8601=minutes)
  created_at=$(date --iso-8601=minutes)
  json -e "this.created_at = '$created_at'; this.startDate = '$startDate';"
}

function stub ( ) {
  zone=$(cat /etc/timezone | nonl)
  dt=$(date --rfc-3339=ns | tr ' ' 'T')
  DIA=$(dia $SETTINGS)
  cat <<EOF | json
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

stub $SETTINGS | fix-dates \
  | add-carbs $CARBS \
  | add-basals $BASALRATES \
  | add-isf $SENSITIVITIES \
  | add-targets $TARGETS \
  | json > $OUTPUT


