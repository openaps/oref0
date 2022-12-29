#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self <TOKEN> <USER> [enact/suggested.json] [none] [15] [carbs|insulin]
EOT

TOKEN=$1
USER=$2
FILE=${3-enact/suggested.json}
SOUND=${4-none}
SNOOZE=${5-15}
ONLYFOR=${6-carbs}
PRIORITY=0
RETRY=60
EXPIRE=600

#echo "Running: $0 $TOKEN $USER $FILE $SOUND $SNOOZE"

if [ -z $TOKEN ] || [ -z $USER ]; then
    print_usage
    exit 1
fi

PREF_VALUE=$(get_prefs_json | jq --raw-output -r .pushover_sound 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ]; then
    SOUND=$PREF_VALUE
fi

PREF_VALUE=$(get_prefs_json | jq .pushover_snooze 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ] && [ "$PREF_VALUE" -eq "$PREF_VALUE" ]; then
    SNOOZE=$PREF_VALUE
fi

PREF_VALUE=$(get_prefs_json | jq --raw-output -r .pushover_only 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ]; then
    ONLYFOR=$PREF_VALUE
fi

PREF_VALUE=$(get_prefs_json | jq .pushover_priority 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ] && [ "$PREF_VALUE" -eq "$PREF_VALUE" ]; then
    PRIORITY=$PREF_VALUE
fi

PREF_VALUE=$(get_prefs_json | jq .pushover_retry 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ] && [ "$PREF_VALUE" -eq "$PREF_VALUE" ]; then
    RETRY=$PREF_VALUE
fi

PREF_VALUE=$(get_prefs_json | jq .pushover_expire 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ] && [ "$PREF_VALUE" -eq "$PREF_VALUE" ]; then
    EXPIRE=$PREF_VALUE
fi

if [ "$SOUND" = "default" ]; then
    SOUND_OPTION=""
else
    SOUND_OPTION="-F sound=$SOUND"
fi

# Set priority to the default if it is an invalid value
if ((PRIORITY < -2)) || ((PRIORITY > 2)); then
    PRIORITY=0
fi

if ((PRIORITY == 2)); then
    PRIORITY_OPTIONS="-F retry=$RETRY -F expire=$EXPIRE"
else
    PRIORITY_OPTIONS=""
fi

#date

#function pushover_snooze {
# check Nightscout to see if another rig has already sent a carbsReq pushover recently
    URL=$NIGHTSCOUT_HOST/api/v1/devicestatus.json?count=100
    if [[ "${API_SECRET}" =~ "token=" ]]; then
        URL="${URL}&${API_SECRET}"
    else
        CURL_AUTH='-H api-secret:'${API_SECRET}
    fi

    if snooze=$(curl --compressed -s ${CURL_AUTH} ${URL} | jq '.[] | select(.snooze=="carbsReq") | select(.date>'$(date +%s -d "10 minutes ago")')' | jq -s .[0].date | noquotes | grep -v null); then
        #echo $snooze
        #echo date -Is -d @$snooze; echo
        touch -d $(date -Is -d @$snooze) monitor/pushover-sent
        #ls -la monitor/pushover-sent | awk '{print $8,$9}'
    fi
#}

if ! file_is_recent "$FILE"; then
    echo "$FILE more than 5 minutes old"
    exit
elif ! cat $FILE | egrep "add'l|maxBolus" > /dev/null; then
    echo -n "No carbsReq. "
elif [[ $ONLYFOR =~ "carb" ]] && ! cat $FILE | egrep "add'l" > /dev/null; then
    echo -n "No carbsReq. "
elif [[ $ONLYFOR =~ "insulin" ]] && ! cat $FILE | egrep "maxBolus" > /dev/null; then
    echo -n "No additional insulin required. "
elif file_is_recent monitor/pushover-sent $SNOOZE; then
    echo -n "Last pushover sent less than $SNOOZE minutes ago. "
else
    curl ---compressed s -F token=$TOKEN -F user=$USER $SOUND_OPTION -F priority=$PRIORITY $PRIORITY_OPTIONS -F "message=$(jq -c "{bg, tick, carbsReq, insulinReq, reason}|del(.[] | nulls)" $FILE) - $(hostname)" https://api.pushover.net/1/messages.json | jq .status| grep 1 >/dev/null && touch monitor/pushover-sent && echo '{"date":'$(epochtime_now)',"device":"openaps://'$(hostname)'","snooze":"carbsReq"}' > /tmp/snooze.json && ns-upload $NIGHTSCOUT_HOST $API_SECRET devicestatus.json /tmp/snooze.json >/dev/null && echo "carbsReq pushover sent."
    echo
fi

# Send to Pushover glances API    
#   For watch face updates once every 10 minutes
#   Works for Apple Watch complications 
#   Not tested for Android Wear notifications yet

# Use file to make sure we don't update glances more often than every 10 mins
# Apple watch disables any complication updates that happen more frequently

source $HOME/.bash_profile
key=${MAKER_KEY:-"null"}
carbsReq=`jq .carbsReq ${FILE}`
tick=`jq .tick ${FILE}`
tick="${tick%\"}"
tick="${tick#\"}"
bgNow=`jq .bg ${FILE}`
delta=`echo "${tick}" | tr -d +`
delta="${delta%\"}"
delta="${delta#\"}"
cob=`jq .COB $FILE`
iob=`jq .IOB $FILE`

#echo "carbsReq=${carbsReq} tick=${tick} bgNow=${bgNow} delta=${delta} cob=${cob} iob=${iob}"
pushoverGlances=$(get_prefs_json | jq -M '.pushoverGlances')

if [ "${pushoverGlances}" == "null" -o "${pushoverGlances}" == "false" ]; then
    echo "pushoverGlances not enabled in preferences.json"
else
  # if pushoverGlances is a number instead of just true, use it to set the minutes allowed between glances
  re='^[0-9]+$'
  if [[ ${pushoverGlances} =~ $re  ]]; then
    glanceDelay=${pushoverGlances}
  else
    glanceDelay=10
  fi
  GLANCES="monitor/last_glance"
  GLUCOSE="monitor/glucose.json"
  if [ ! -f $GLANCES ]; then
    # First time through it will get created 1h old so it'll fire
    touch $GLANCES && touch -r $GLANCES -d '-60 mins' $GLANCES
  fi

  if snooze=$(curl --compressed -s ${CURL_AUTH} ${URL} | jq '.[] | select(.snooze=="glance") | select(.date>'$(date +%s -d "$glanceDelay minutes ago")')' | jq -s .[0].date | noquotes | grep -v null); then
        #echo $snooze
        #echo date -Is -d @$snooze; echo
        touch -d $(date -Is -d @$snooze) $GLANCES
        #ls -la $GLANCES | awk '{print $8,$9}'
  fi

  if test `find $GLANCES -mmin +$glanceDelay` || cat $FILE | egrep "add'l" >/dev/null
  then
    curTime=$(ls -l  --time-style=+"%l:%M" ${FILE} | awk '{printf ($6)}')

    lastDirection=`jq -M '.[0] .direction' $GLUCOSE`
    lastDirection="${lastDirection%\"}"
    lastDirection="${lastDirection#\"}"

    rate=`jq -M '.rate' monitor/temp_basal.json`
    duration=`jq -M '.duration' monitor/temp_basal.json`
    #echo lastDirection=$lastDirection

    if [ "${lastDirection}" == "SingleUp" ]; then
      direction="↑"
    elif [ "${lastDirection}" == "FortyFiveUp" ]; then
      direction="↗"
    elif [ "${lastDirection}" == "DoubleUp" ]; then
      direction="↑↑"
    elif [ "${lastDirection}" == "SingleDown" ]; then
      direction="↓"
    elif [ "${lastDirection}" == "FortyFiveDown" ]; then
      direction="↘"
    elif [ "${lastDirection}" == "DoubleDown" ]; then
      direction="↓↓"
    else
      direction="→" # default for NONE or Flat
    fi

    title="${bgNow} ${tick} ${direction}      @ ${curTime}"
    text="IOB ${iob}, COB ${cob}"
    if cat $FILE | egrep "add'l" >/dev/null; then
      carbsMsg="${carbsReq}g req "
    fi
    subtext="$carbsMsg${rate}U/h ${duration}m"

#    echo "pushover glance text=${text}  subtext=${subtext}  delta=${delta} title=${title}  battery percent=${battery}"
    curl --compressed -s -F "token=$TOKEN" -F "user=$USER" -F "text=${text}" -F "subtext=${subtext}" -F "count=$bgNow" -F "percent=${battery}" -F "title=${title}"   https://api.pushover.net/1/glances.json | jq .status| grep 1 >/dev/null && echo '{"date":'$(epochtime_now)',"device":"openaps://'$(hostname)'","snooze":"glance"}' > /tmp/snooze.json && ns-upload $NIGHTSCOUT_HOST $API_SECRET devicestatus.json /tmp/snooze.json >/dev/null && echo "Glance uploaded and snoozed"
    touch $GLANCES
  else
    echo -n "Pushover glance last updated less than $glanceDelay minutes ago @ "
    ls -la $GLANCES | awk '{print $8}'
  fi
fi

# Send IFTTT maker event "carbs-required" if additional carbs are required
#   and if environment variable "MAKER_KEY" is set. This is the IFTTT webhooks Maker key
#   https://ifttt.com/maker_webhooks
#   The "carbs-required" event can then be used with a IFTTT recipe to perform an action
#   based on carbs required. A good use case is to use the IFTTT phone action to get a phone
#   call with this event that will read out in human language the additional carbs and other
#   vital facts. It will leave a voice mail if not answered.

if ! [ -z "$MAKER_KEY" ] && [[ "$MAKER_KEY" != "null" ]] && cat $FILE | egrep "add'l"; then
  if file_is_recent monitor/ifttt-sent 60; then
     echo "carbsReq=${carbsReq} but last IFTTT event sent less than 60 minutes ago."
  else
     message="Carbs required = ${carbsReq}. Glucose = $bgNow Insulin on board = $iob Carbs on board = $cob grams."
     echo "posting message to carbs-required ... message=$message"

     ifttt="monitor/ifttt.json"
     values="{ \"value1\":\"$message\" }"

     echo $values > $ifttt

     curl --compressed --request POST \
     --header 'Content-Type: application/json' \
     -d @$ifttt  \
     https://maker.ifttt.com/trigger/carbs-required/with/key/${key} && touch monitor/ifttt-sent
  fi
fi

