#!/bin/bash
MAC=$1

if ! ( rfcomm show hci0 | grep -q $MAC ) ; then
   sudo rfcomm bind hci0 $MAC
fi 

#Status for Pancreabble Urchin
if [[ $(jq .urchin_loop_status pancreoptions.json) != "true" ]]; then
	echo {"\"message\": "\"loop status at "'$(date +%-I:%M%P)'": Running\"} > upload/urchin-status.json
fi 
if [[ $(jq .urchin_iob pancreoptions.json) != "true" ]]; then
   echo {"\"message\": "\""$(date +%R)": IOB: $(jq .openaps.iob.iob upload/ns-status.json) - BasalIOB: $(jq .openaps.iob.basaliob upload/ns-status.json)\"} > upload/urchin-status.json
fi

#Notification Status
if [[ $(jq .Notify_Temp_Basal pancreoptions.json) = "true" ]]; then
   if [[ $(jq .rate enact/suggested.json) != null ]]; then
      if [[ $(jq .rate enact/suggested.json) != $tempb ]]; then
         openaps use pbbl notify "Temp Basal" "set temp basal: $(jq .rate enact/suggested.json) for $(jq .duration enact/suggested.json) minutes"
         tempb = $(jq .rate enact/suggested.json)
      fi
   fi
fi

if [[ $(jq .Notify_Battery pancreoptions.json) = "true" ]]; then
   if [[ $(jq .battery monitor/edison-battery.json) -le $(jq .Notify_Battery_Alarm pancreoptions.json) ]]; then
      alarms = `jq .Notify_Battery_Alarm_Silence pancreoptions.json`
	  let "time = alarms * 60"
      if [[ $time -ge $date ]]; then
         openaps use pbbl notify "Edison" "Edison Battery at: $(jq .battery monitor/edison-battery.json)%"
	     tempbatt = $(date)
      fi   
   fi
fi   
