#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
EOT

CGM="$(get_pref_string .cgm)"
CGM_LOOPDIR="$(get_pref_string .cgm_loop_path)"

cd $CGM_LOOPDIR

function echo_glucose {
    echo ">>>>RESULTS<<<<" \
    && json -f monitor/glucose-raw-merge.json -a sgv raw dateString | head -n 4
}

function wait_until_expected {
    oref0-dex-wait-until-expected monitor/glucose-zoned.json 5.1
}

function glucose_report {
    openaps report invoke monitor/glucose-oref0.json monitor/glucose-zoned.json monitor/glucose-zoned-merge.json monitor/glucose-raw-merge.json
}

function upload {
    report invoke nightscout/recent-missing-entries.json nightscout/uploaded-entries.json
}

if [[ "${CGM,,}" == "mdt" ]]; then
    openaps report invoke monitor/cgm-mm-glucosedirty.json monitor/cgm-mm-glucosetrend.json cgm/cgm-glucose.json
elif [[ ${CGM,,} =~ "g4-upload" ]] ||  [[ ${CGM,,} =~ "shareble" ]]; then
    wait_until_expected \
    && time glucose_report \
    && echo_glucose \
    && (openaps upload-first || echo upload first failed) \
    && (upload || echo cgm upload failed) \
    && (openaps maybe-extras || echo cgm extras failed)
else
    openaps report invoke raw-cgm/raw-entries.json cgm/cgm-glucose.json
fi
