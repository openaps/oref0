#!/bin/bash

TOKEN=$1
USER=$2
FILE={$3-enact/smb-suggested.json}
SOUND={$4-none}
SNOOZE={$5-15}

if [ -z $TOKEN ] || [ -z $USER ]; then
      echo "Usage: $0 <TOKEN> <USER> [enact/smb-suggested.json] [none] [15]"
fi

if ! find monitor/ -mmin -$SNOOZE -ls | grep pushover-sent && cat $FILE | egrep "add'l|maxBolus"; then
    curl -s -F "token=$TOKEN" -F "user=$USER" -F "sound=$SOUND" -F "message=$(jq -c "{bg, tick, carbsReq, insulinReq, reason}|del(.[] | nulls)" $FILE)" https://api.pushover.net/1/messages.json && touch monitor/pushover-sent
fi
