#!/bin/bash

TOKEN=$1
USER=$2
FILE=${3-enact/suggested.json}
SOUND=${4-none}   lastDirection=`jq -M '.[0] .direction' $GLUCOSE`

    echo lastDirection=$lastDirection

    if [ "${lastDirection}" == "SingleUp" ]; then
      direction="+"
    elif [ "${lastDirection}" == "FortyFiveUp" ]; then
      direction="++"
    elif [ "${lastDirection}" == "DoubleUp" ]; then
      direction="+++"
    elif [ "${lastDirection}" == "SingleDown" ]; then
      direction="-"
    elif [ "${lastDirection}" == "FortyFiveDown" ]; then
      direction="--"
    elif [ "${lastDirection}" == "DoubleDown" ]; then
      direction="---"
    else
      direction="" # default for NONE or Flat
    fi


SNOOZE=${5-15}
ONLYFOR=${6-carbs}

#echo "Running: $0 $TOKEN $USER $FILE $SOUND $SNOOZE"

if [ -z $TOKEN ] || [ -z $USER ]; then
    echo "Usage: $0 <TOKEN> <USER> [enact/suggested.json] [none] [15] [carbs|insulin]"
    exit
fi

date
if find monitor/ -mmin -$SNOOZE | grep -q pushover-sent; then
    echo "Last pushover sent less than $SNOOZE minutes ago."
elif ! find $FILE -mmin -5 | grep -q $FILE; then
    echo "$FILE more than 5 minutes old"
    exit
elif ! cat $FILE | egrep "add'l|maxBolus"; then
    echo "No additional carbs or bolus required."
elif [[ $ONLYFOR =~ "carb" ]] && ! cat $FILE | egrep "add'l"; then
    echo "No additional carbs required."   lastDirection=`jq -M '.[0] .direction' $GLUCOSE`

    echo lastDirection=$lastDirection

    if [ "${lastDirection}" == "SingleUp" ]; then
      direction="+"
    elif [ "${lastDirection}" == "FortyFiveUp" ]; then
      direction="++"
    elif [ "${lastDirection}" == "DoubleUp" ]; then
      direction="+++"
    elif [ "${lastDirection}" == "SingleDown" ]; then
      direction="-"
    elif [ "${lastDirection}" == "FortyFiveDown" ]; then
      direction="--"
    elif [ "${lastDirection}" == "DoubleDown" ]; then
      direction="---"
    else
      direction="" # default for NONE or Flat
    fi


elif [[ $ONLYFOR =~ "insulin" ]] && ! cat $FILE | egrep "maxBolus"; then
    echo "No additional insulin required."
else
    curl -s -F "token=$TOKEN" -F "user=$USER" -F "sound=$SOUND" -F "message=$(jq -c "{bg, tick, carbsReq, insulinReq, reason}|del(.[] | nulls)" $FILE) - $(hostname)" https://api.pushover.net/1/messages.json && touch monitor/pushover-sent
fi

# Send to Pushover glances API    lastDirection=`jq -M '.[0] .direction' $GLUCOSE`

    echo lastDirection=$lastDirection

    if [ "${lastDirection}" == "SingleUp" ]; then
      direction="+"
    elif [ "${lastDirection}" == "FortyFiveUp" ]; then
      direction="++"
    elif [ "${lastDirection}" == "DoubleUp" ]; then
      direction="+++"
    elif [ "${lastDirection}" == "SingleDown" ]; then
      direction="-"
    elif [ "${lastDirection}" == "FortyFiveDown" ]; then
      direction="--"
    elif [ "${lastDirection}" == "DoubleDown" ]; then
      direction="---"
    else
      direction="" # default for NONE or Flat
    fi


#   For watch face updates once every 10 minutes
#   Works for Apple Watch complications 
#   Not tested for Android Wear notifications yet

# Use file to make sure we don't update glances more often than every 10 mins
# Apple watch disables any complication updates that happen more frequently

source $HOME/.bash_profile
key=${MAKER_KEY:-"null"}
carbsReq=`jq .carbsReq ${FILE}`
tick=`jq .tick ${FILE}`
bgNow=`jq .bg ${FILE}`
delta=`echo "${tick}" | tr -d +`
delta="${delta%\"}"
delta="${delta#\"}"
cob=`jq .COB $FILE`
iob=`jq .IOB $FILE`
   lastDirection=`jq -M '.[0] .direction' $GLUCOSE`

    echo lastDirection=$lastDirection

    if [ "${lastDirection}" == "SingleUp" ]; then
      direction="+"
    elif [ "${lastDirection}" == "FortyFiveUp" ]; then
      direction="++"
    elif [ "${lastDirection}" == "DoubleUp" ]; then
      direction="+++"
    elif [ "${lastDirection}" == "SingleDown" ]; then
      direction="-"
    elif [ "${lastDirection}" == "FortyFiveDown" ]; then
      direction="--"
    elif [ "${lastDirection}" == "DoubleDown" ]; then
      direction="---"
    else
      direction="" # default for NONE or Flat
    fi


#echo "carbsReq=${carbsReq} tick=${tick} bgNow=${bgNow} delta=${delta} cob=${cob} iob=${iob}"
pushoverGlances=$(cat preferences.json | jq -M '.pushoverGlances')

if [ "${pushoverGlances}" == "null" -o "${pushoverGlances}" == "false" ]; then
    echo "pushoverGlances not enabled in preferences.json"   lastDirection=`jq -M '.[0] .direction' $GLUCOSE`

    echo lastDirection=$lastDirection

    if [ "${lastDirection}" == "SingleUp" ]; then
      direction="+"
    elif [ "${lastDirection}" == "FortyFiveUp" ]; then
      direction="++"
    elif [ "${lastDirection}" == "DoubleUp" ]; then
      direction="+++"
    elif [ "${lastDirection}" == "SingleDown" ]; then
      direction="-"
    elif [ "${lastDirection}" == "FortyFiveDown" ]; then
      direction="--"
    elif [ "${lastDirection}" == "DoubleDown" ]; then
      direction="---"
    else
      direction="" # default for NONE or Flat
    fi


else
  GLANCES="monitor/last_glance"
  GLUCOSE="monitor/glucose.json"
  if [ ! -f $GLANCES ]; then
    # First time through it will get created older than 10 minutes so it'll fire
    touch $GLANCES && touch -r $GLANCES -d '-11 mins' $GLANCES
  fi

  if test `find $GLANCES -mmin +10`
  then
    enactTime=$(ls -l  --time-style=+"%l:%M" ${FILE} | awk '{printf ($6)}')

    lastDirection=`jq -M '.[0] .direction' $GLUCOSE`

    #echo lastDirection=$lastDirection

    if [ "${lastDirection}" == "SingleUp" ]; then
      direction="+"
    elif [ "${lastDirection}" == "FortyFiveUp" ]; then
      direction="++"
    elif [ "${lastDirection}" == "DoubleUp" ]; then
      direction="+++"
    elif [ "${lastDirection}" == "SingleDown" ]; then
      direction="-"
    elif [ "${lastDirection}" == "FortyFiveDown" ]; then
      direction="--"
    elif [ "${lastDirection}" == "DoubleDown" ]; then
      direction="---"
    else
      direction="" # default for NONE or Flat
    fi

    if [ test cat $FILE | egrep "add'l" ]; then
      subtext="cr ${carbsReq}g"
    else
      subtext="e${enactTime}"
    fi
    text="${bgNow}${direction}"
    title="cob ${cob}, iob ${iob}"

#    echo "pushover glance text=${text}  subtext=${subtext}  delta=${delta} title=${title}  battery percent=${battery}"
    curl -s -F "token=$TOKEN" -F "user=$USER" -F "text=${text}" -F "subtext=${subtext}" -F "count=$bgNow" -F "percent=${battery}" -F "title=${title}"   https://api.pushover.net/1/glances.json
    touch $GLANCES
  fi
fi

# Send IFTTT maker event "carbs-required" if additional carbs are required
#   and if environment variable "MAKER_KEY" is set. This is the IFTTT webhooks Maker key
#   https://ifttt.com/maker_webhooks
#   The "carbs-required" event can then be used with a IFTTT recipe to perform an action
#   based on carbs required. A good use case is to use the IFTTT phone action to get a phone
#   call with this event that will read out in human language the additional carbs and other
#   vital facts. It will leave a voice mail if not answered.

if [[ "$MAKER_KEY" != "null" ]] && cat $FILE | egrep "add'l"; then
  if find monitor/ -mmin -15 | grep -q ifttt-sent; then
     echo "carbsReq=${carbsReq} but last IFTTT event sent less than 15 minutes ago."
  else
     message="Carbs required = ${carbsReq}. Glucose = $bgNow Insulin on board = $iob Carbs on board = $cob grams."
     echo "posting message to carbs-required ... message=$message"

     ifttt="monitor/ifttt.json"
     values="{ \"value1\":\"$message\" }"

     echo $values > $ifttt

     curl --request POST \
     --header 'Content-Type: application/json' \
     -d @$ifttt  \
     https://maker.ifttt.com/trigger/carbs-required/with/key/${key} && touch monitor/ifttt-sent
  fi
fi

