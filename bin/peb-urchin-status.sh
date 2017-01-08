#!/bin/bash
MAC=$1

if ! ( rfcomm show hci0 | grep -q $MAC ) ; then
   sudo rfcomm bind hci0 $MAC
fi 

#Status for Pancreabble Urchin
#echo {"\"message\": "\"loop status at "'$(date +%-I:%M%P)'": Running\"} > upload/urchin-status.json
echo {"\"message\": "\""$(date +%R)": IOB: $(jq .openaps.iob.iob upload/ns-status.json) - BasalIOB: $(jq .openaps.iob.basaliob upload/ns-status.json)\"} > upload/urchin-status.json
