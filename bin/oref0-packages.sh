#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self

Downloads Packages required for oref0 and dependencies using apt-get
This is normally invoked from oref0-install.sh.
EOT

# TODO: remove the `Acquire::ForceIPv4=true` once Debian's mirrors work reliably over IPv6
echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4

apt-get install -y sudo
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y git watchdog strace tcpdump screen acpid vim locate lm-sensors || die "Couldn't install packages"

# We require jq >= 1.5 for --slurpfile for merging preferences. Debian Jessie ships with 1.4
if is_debian_jessie; then
   sudo apt-get -y -t jessie-backports install jq || die "Couldn't install jq from jessie-backports"
else
   sudo apt-get -y install jq || die "Couldn't install jq"
fi

# install/upgrade to latest node 8 if neither node 8 nor node 10+ LTS are installed
if ! nodejs --version | grep -e 'v8\.' -e 'v1[02468]\.' ; then
        sudo bash -c "curl -sL https://deb.nodesource.com/setup_8.x | bash -" || die "Couldn't setup node 8"
        sudo apt-get install -y nodejs || die "Couldn't install nodejs"
fi

# TODO: remove all openaps references and don't install openaps anymore
sudo pip install -U openaps || die "Couldn't install openaps toolkit"
sudo pip install -U openaps-contrib || die "Couldn't install openaps-contrib"
sudo openaps-install-udev-rules || die "Couldn't run openaps-install-udev-rules"
sudo activate-global-python-argcomplete || die "Couldn't run activate-global-python-argcomplete"
echo openaps installed
openaps --version

echo oref0 packages installed. Version branch=`git rev-parse --abbrev-ref HEAD` short=`git rev-parse --short HEAD` long=`git rev-parse HEAD`

