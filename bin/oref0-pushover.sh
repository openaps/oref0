#!/bin/bash

TOKEN=$1
USER=$2
FILE=${3-enact/smb-suggested.json}
SOUND=${4-none}
SNOOZE=${5-15}
ONLYFOR=${6-carbs}

#echo "Running: $0 $TOKEN $USER $FILE $SOUND $SNOOZE"

if [ -z $TOKEN ] || [ -z $USER ]; then
    echo "Usage: $0 <TOKEN> <USER> [enact/smb-suggested.json] [none] [15] [carbs|insulin]"
    exit
fi

date
if find monitor/ -mmin -$SNOOZE | grep -q pushover-sent; then
    echo "Last pushover sent less than $SNOOZE minutes ago."
elif ! find $FILE -mmin -5 | grep -q $FILE; then
    echo "$FILE more than 5 minutes old"
elif ! cat $FILE | egrep "add'l|maxBolus"; then
    echo "No additional carbs or bolus required."
elif [[ $ONLYFOR =~ "carb" ]] && ! cat $FILE | egrep "add'l"; then
    echo "No additional carbs required."
elif [[ $ONLYFOR =~ "insulin" ]] && ! cat $FILE | egrep "maxBolus"; then
    echo "No additional insulin required."
else
    curl -s -F "token=$TOKEN" -F "user=$USER" -F "sound=$SOUND" -F "message=$(jq -c "{bg, tick, carbsReq, insulinReq, reason}|del(.[] | nulls)" $FILE) - $(hostname)" https://api.pushover.net/1/messages.json && touch monitor/pushover-sent
fi

# Enhance to send to pushover glances API
#   For watch face updates once every 10 minutes
#   Works for apple watch complications
#   Not tested fo android wear notifications yet

# Use file to make sure we don't update glances more often than every 10 mins
# Apple watch disables any complication updates that happen more frequently

pushoverGlances=$(cat preferences.json | jq -M '.pushoverGlances')

if [ "${pushoverGlances}" == "null" -o "${pushoverGlances}" == "false" ]; then
    echo "No preference or false preference for pushoverGlances"
  exit
fi


GLANCES="monitor/last_glance"
GLUCOSE="monitor/glucose.json"
if [ ! -f $GLANCES ]; then
  # First time through it will get created older than 10 minutes so it'll fire
  touch $GLANCES && touch -r $GLANCES -d '-11 mins' $GLANCES
fi

if test `find $GLANCES -mmin +10`
then
  BAT="monitor/edison-battery.json"
  carbsReq=`jq .carbsReq $FILE`
  bgNow=$(cat $GLUCOSE | jq -M '.[0].glucose')
  bgLast=$(cat $GLUCOSE | jq -M '.[1].glucose')
  COB=`jq .COB $FILE`

  IOB=$(cat $FILE | jq -M '.IOB')
  IOB="${IOB%\"}"
  IOB="${IOB#\"}"
  enactTime=$(ls -l  --time-style=+"%l:%M" ${FILE} | awk '{printf ($6)}')
  battery=0
  if [ -e $BAT ]; then
    battery=$(cat $BAT | jq -M '.battery')
    battery="${battery%\"}"
    battery="${battery#\"}"
  fi



  direction=""
  if [ ${bgLast} -gt 0 ]; then
    delta=$(expr ${bgNow} - ${bgLast})

    if [ ${delta} -gt 8 ]; then
      direction="++"
    elif [ ${delta} -gt 3 ]; then
      direction="+"
    elif [ ${delta} -gt -3 ]; then
      direction=""
    elif [ ${delta} -gt -8 ]; then
      direction="-"
    else
      direction="--"
    fi
  fi
  if [ test cat $FILE | egrep "add'l" ]; then  
    subtext="cr ${carbsReq}g"
  else
    subtext="e${enactTime}"
  fi
  text="${bgNow}${direction}"
  title="cob ${COB}, iob ${IOB}"

  echo "pushover glance text=${text}  subtext=${subtext}  delta=${delta} bgLast=${bgLast}  title=${title}  battery percent=${battery}"
  touch $GLANCES
  curl -s -F "token=$TOKEN" -F "user=$USER" -F "text=${text}" -F "subtext=${subtext}" -F "count=$bgNow" -F "percent=${battery}" -F "title=${title}"   https://api.pushover.net/1/glances.json
fi
