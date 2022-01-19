#!/usr/bin/env bash

die() {
    echo "$@"
    exit 1
}

# TODO: remove the `Acquire::ForceIPv4=true` once Debian's mirrors work reliably over IPv6
echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4

apt-get install -y sudo
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y git python python-dev software-properties-common python-numpy python-pip watchdog strace tcpdump screen acpid vim locate lm-sensors || die "Couldn't install packages"

# We require jq >= 1.5 for --slurpfile for merging preferences. Debian Jessie ships with 1.4
if cat /etc/os-release | grep 'PRETTY_NAME="Debian GNU/Linux 8 (jessie)"' &> /dev/null; then
   sudo apt-get -y -t jessie-backports install jq || die "Couldn't install jq from jessie-backports"
else
   sudo apt-get -y install jq || die "Couldn't install jq"
fi

# install/upgrade to latest node 15
echo installing up to date nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
source ~/.bashrc
nvm install 15.14.0
nvm install 'lts/*' --reinstall-packages-from=current
nvm install-latest-npm


sudo pip install -U openaps || die "Couldn't install openaps toolkit"
sudo pip install -U openaps-contrib || die "Couldn't install openaps-contrib"
sudo openaps-install-udev-rules || die "Couldn't run openaps-install-udev-rules"
sudo activate-global-python-argcomplete || die "Couldn't run activate-global-python-argcomplete"
sudo npm install -g json || die "Couldn't install npm json"
echo openaps installed
openaps --version
