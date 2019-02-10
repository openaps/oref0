#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
EOT

CGM="$(get_pref_string .cgm)"
if [[ "${CGM,,}" == "mdt" ]]; then
    (echo -n MDT cgm data retrieve \
        && oref0-monitor-cgm 2>/dev/null >/dev/null \
        && grep -q glucose cgm/cgm-glucose.json \
        && echo d) \
    && cp -pu cgm/cgm-glucose.json cgm/glucose.json \
    && cp -pu cgm/glucose.json monitor/glucose-unzoned.json \
    && (echo -n MDT cgm data reformat \
        && openaps report invoke monitor/glucose.json nightscout/glucose.json 2>/dev/null >/dev/null \
        && echo ted)
else
    oref0-monitor-cgm 2>&1 | tail -1 \
    && grep -q glucose cgm/cgm-glucose.json \
    && cp -pu cgm/cgm-glucose.json cgm/glucose.json
    cp -pu cgm/glucose.json monitor/glucose.json
fi