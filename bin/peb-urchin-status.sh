#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self <MAC>
Collect status information to display on a Pebble smartwatch. Runs from
crontab, if you indicated you have a Pebble during oref0-setup.
EOT

MAC=$1

if ! ( rfcomm show hci0 | grep -q $MAC ) ; then
   sudo rfcomm bind hci0 $MAC
fi 

#Status for Pancreabble Urchin
if [[ $(jq .urchin_loop_status pancreoptions.json) = "true" ]]; then
	echo {"\"message\": "\"loop status at "'$(date +%-I:%M%P)'": Running\"} > upload/urchin-status.json
fi 
if [[ $(jq .urchin_iob pancreoptions.json) = "true" ]]; then
   echo {"\"message\": "\""$(date +%R)": IOB: $(jq .openaps.iob.iob upload/ns-status.json)\"} > upload/urchin-status.json
fi
if [[ $(jq .urchin_temp_rate pancreoptions.json) = "true" ]]; then
   echo {"\"message\": "\""$(date +%-I:%M%P)": Basal: $(jq .rate monitor/temp_basal.json) U/hr for $(jq .duration monitor/temp_basal.json) mins\"} > upload/urchin-status.json
fi

#Notification Status
if [[ $(jq .notify_temp_basal pancreoptions.json) = "true" ]]; then
   if [[ $(jq .rate enact/suggested.json) != null ]]; then
      openaps use pbbl notify "Set Temp Basal" "at $(date +%-I:%M%P): $(jq .rate enact/suggested.json) for $(jq .duration enact/suggested.json) minutes"
   fi
fi



#decide to run urchin loop or not
if [[ $(jq .urchin_loop_on pancreoptions.json) = "true" ]]; then
   openaps invoke upload/urchin-data.json \
   && openaps use pbbl send_urchin_data upload/urchin-data.json
fi
