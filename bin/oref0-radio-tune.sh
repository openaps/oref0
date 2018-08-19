#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self
Determine the optimum frequency to communicate with the pump and write
the output to monitor/mmtune.json and monitor/medtronic_frequency.ini
EOF

function mmtune_Go() {
  set -o pipefail
  if ( grep "WW" pump.ini ); then
    Go-mmtune -ww | tee monitor/mmtune.json
  else
    Go-mmtune | tee monitor/mmtune.json
  fi
}

echo {} > monitor/mmtune.json
echo -n "mmtune: " && mmtune_Go >&3 2>&3
# if mmtune.json is empty, re-run it and display output
if ! [ -s monitor/mmtune.json ]; then
    mmtune_Go
fi
#Read and zero pad best frequency from mmtune, and store/set it so Go commands can use it,
#but only if it's not the default frequency
if ! $([ -s monitor/mmtune.json ] && jq -e .usedDefault monitor/mmtune.json); then
  freq=`jq -e .setFreq monitor/mmtune.json | tr -d "."`
  while [ ${#freq} -ne 9 ];
    do
     freq=$freq"0"
    done
  #Make sure we don't zero out the medtronic frequency. It will break everything.
  if [ $freq != "000000000" ] ; then
       echo $freq > monitor/medtronic_frequency.ini
  fi
fi

