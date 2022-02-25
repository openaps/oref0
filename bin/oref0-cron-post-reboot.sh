#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
Do all the things that oref0 does once per reboot, based on config files. This
should run from cron, in the myopenaps directory.
EOT

assert_cwd_contains_ini

CGM="$(get_pref_string .cgm)"
XDRIP_PATH="$(get_pref_string .xdrip_path)"
ttyport="$(get_pref_string .ttyport)"

if [[ "${CGM,,}" =~ "xdrip" ]]; then
    python "$XDRIP_PATH/xDripAPS.py" &
fi

oref0-delete-future-entries &

(
    cd ~/src/oref0/www
    export FLASK_APP=app.py
    flask run -p 80 --host=0.0.0.0 | tee -a /var/log/openaps/flask.log
) &
