#!/usr/bin/env bash 
 
# Since the Edison does not have an internal clock 
# after a reboot if you do not have the correct time your date will be older than  
# the time on the CGM data in the monitor folder.  
# Currently all the checks for time in the system is looking at data being older than current  
# time 
# This will delete all the data in the  
# monitor directory. Allowing oref0 to gather all of the data again in pump-loop 

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
EOT

NEWTIME=$(to_epochtime $(jq .[1].display_time monitor/glucose.json))
TIME=$(to_epochtime '5 minutes')

echo $NEWTIME 
echo $TIME

if [ $NEWTIME -gt $TIME ]; then 
    echo CGM Time is newer than Edison Time$'\n'Deleting All Monitor Files
    sudo rm -rf monitor/*
elif [ $NEWTIME -lt $TIME ]; then  
	echo "No Newer CGM Data found" 
fi
