#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOF
Usage: $self
Determine the optimum frequency to communicate with the pump and write
the output to monitor/mmtune.json and monitor/medtronic_frequency.ini
EOF

assert_cwd_contains_ini

export MEDTRONIC_PUMP_ID=`get_pref_string .pump_serial | tr -cd 0-9`
export MEDTRONIC_FREQUENCY=`cat monitor/medtronic_frequency.ini`

OREF0_DEBUG=${OREF0_DEBUG:-0}
if [[ "$OREF0_DEBUG" -ge 1 ]] ; then
  exec 3>&1
else
  exec 3>/dev/null
fi
if [[ "$OREF0_DEBUG" -ge 2 ]] ; then
  exec 4>&1
  set -x
else
  exec 4>/dev/null
fi

function mmtune_Go() {
  set -o pipefail
  if [ "$(get_pref_string .radio_locale '')" == "WW" ]; then
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
if [ -s monitor/mmtune.json ]; then 
  if ! $(jq -e .usedDefault monitor/mmtune.json); then
    freq=`jq -e .setFreq monitor/mmtune.json | tr -d "."`
    while [ ${#freq} -ne 9 ];
      do
       freq=$freq"0"
    done
    #Make sure we don't zero out the medtronic frequency. It will break everything.
    if [ $freq != "000000000" ] ; then
       echo $freq > monitor/medtronic_frequency.ini
    fi

    grep -v setFreq monitor/mmtune.json | grep -A2 $(json -a setFreq -f monitor/mmtune.json) | while read line
        do echo -n "$line "
    done
  fi
else
  die "monitor/mmtune.json is empty or does not exist"
fi

echo

