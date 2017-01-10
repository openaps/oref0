#!/bin/bash
MAC=$1

if ! ( rfcomm show hci0 | grep -q $MAC ) ; then
   sudo rfcomm bind hci0 $MAC
fi 

#Status for Pancreabble Urchin
if [[ $(jq .urchin_loop_status pancreoptions.json) = "true" ]]; then
	echo {"\"message\": "\"loop status at "'$(date +%-I:%M%P)'": Running\"} > upload/urchin-status.json
fi 
if [[ $(jq .urchin_iob pancreoptions.json) = "true" ]]; then
   echo {"\"message\": "\""$(date +%R)": IOB: $(jq .openaps.iob.iob upload/ns-status.json) - BasalIOB: $(jq .openaps.iob.basaliob upload/ns-status.json)\"} > upload/urchin-status.json
fi

#Notification Status
if [[ $(jq .notify_temp_basal pancreoptions.json) = "true" ]]; then
   if [[ $(jq .rate enact/suggested.json) != null ]]; then
      openaps use pbbl notify "Set Temp Basal" "at $(date +%-I:%M%P): $(jq .rate enact/suggested.json) for $(jq .duration enact/suggested.json) minutes"
   fi
fi
