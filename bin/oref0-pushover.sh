#!/bin/bash

TOKEN=$1
USER=$2
FILE=${3-enact/smb-suggested.json}
SOUND=${4-none}
SNOOZE=${5-15}
ONLYFOR=${6-carbs}
PRIORITY=0
RETRY=60
EXPIRE=600

PREF_FILE=preferences.json

#echo "Running: $0 $TOKEN $USER $FILE $SOUND $SNOOZE"

if [ -z $TOKEN ] || [ -z $USER ]; then
    echo "Usage: $0 <TOKEN> <USER> [enact/smb-suggested.json] [none] [15] [carbs|insulin]"
    exit
fi

PREF_VALUE=$(cat $PREF_FILE | jq --raw-output -r .pushover_sound 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ]; then
    SOUND=$PREF_VALUE
fi

PREF_VALUE=$(cat $PREF_FILE | jq .pushover_snooze 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ] && [ "$PREF_VALUE" -eq "$PREF_VALUE" ]; then
    SNOOZE=$PREF_VALUE
fi

PREF_VALUE=$(cat $PREF_FILE | jq --raw-output -r .pushover_only 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ]; then
    ONLYFOR=$PREF_VALUE
fi

PREF_VALUE=$(cat $PREF_FILE | jq .pushover_priority 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ] && [ "$PREF_VALUE" -eq "$PREF_VALUE" ]; then
    PRIORITY=$PREF_VALUE
fi

PREF_VALUE=$(cat $PREF_FILE | jq .pushover_retry 2>/dev/null)

if [ ! -z $PREF_VALUE ] && [ $PREF_VALUE != "null" ] && [ "$PREF_VALUE" -eq "$PREF_VALUE" ]; then
    RETRY=$PREF_VALUE
fi

PREF_VALUE=$(cat $PREF_FILE | jq .pushover_expire 2>/dev/null)

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
    curl -s -F token=$TOKEN -F user=$USER $SOUND_OPTION -F priority=$PRIORITY $PRIORITY_OPTIONS -F "message=$(jq -c "{bg, tick, carbsReq, insulinReq, reason}|del(.[] | nulls)" $FILE) - $(hostname)" https://api.pushover.net/1/messages.json && touch monitor/pushover-sent
    echo
fi
