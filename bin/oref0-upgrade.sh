#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self
This program is used to install all needed applications for people who have just updated their source code.
This should be called at 15-minute intervals.
EOT

function verify_installed () {
    dpkg-query --list $1 || apt-get install -y $1
}

verify_installed socat
verify_installed ntp

if [ ! -e /usr/local/bin/oref0-shared-node-loop ] ; then 
    ln -s ../lib/node_modules/oref0/bin/oref0-shared-node-loop.sh /usr/local/bin/oref0-shared-node-loop 
fi
