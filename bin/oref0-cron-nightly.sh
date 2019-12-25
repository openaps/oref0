#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Do all the things that oref0 does once per night, based on config files.
Currently this just means autotune and uploading profile to Nightscout. 
This should run from cron, in the myopenaps directory. By default, this 
happens at 4:05am every night.
EOT

assert_cwd_contains_ini

ENABLE="$(get_pref_string .enable)"
NIGHTSCOUT_HOST="$(get_pref_string .nightscout_host)"
directory="$PWD"

if [[ $ENABLE =~ autotune ]]; then
    # autotune nightly at 4:05am using data from NS
    echo "=== Running Autotune at `date` === " | tee -a /var/log/openaps/autotune.log
    (oref0-autotune -d=$directory -n=$NIGHTSCOUT_HOST && \
        cat $directory/autotune/profile.json | jq . | grep -q start && \
        cp $directory/autotune/profile.json $directory/settings/autotune.json && \
        echo Sleeping 60s to let oref0-ns-loop generate a new profile.json to upload && sleep 60 && \
        oref0-upload-profile settings/profile.json $NIGHTSCOUT_HOST $API_SECRET) 2>&1 | tee -a /var/log/openaps/autotune.log &
fi
