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
