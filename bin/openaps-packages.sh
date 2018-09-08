#!/bin/bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

usage "$@" <<EOT
Usage: $self

Downloads OpenAPS packages using pip, and dependencies using apt-get and npm.
This is normally invoked from openaps-install.sh.
EOT

# TODO: remove the `Acquire::ForceIPv4=true` once Debian's mirrors work reliably over IPv6
echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4

apt-get install -y sudo
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y git python python-dev software-properties-common python-numpy python-pip watchdog strace tcpdump screen acpid vim locate jq lm-sensors || die "Couldn't install packages"
if getent passwd edison > /dev/null; then
    sudo apt-get -o Acquire::ForceIPv4=true install -y nodejs-legacy || die "Couldn't install nodejs-legacy"
fi
#if ! sudo apt-get install -y npm; then
# install/upgrade to latest node 8 if neither node 8 nor node 10+ LTS are installed
if ! nodejs --version |grep -e 'v1[02468]\.' -e 'v8\.'; then
    #if grep -qa "Explorer HAT" /proc/device-tree/hat/product &>/dev/null ; then
    #    mkdir $HOME/src/node && cd $HOME/src/node
    #    wget https://nodejs.org/dist/v8.11.4/node-v8.11.4-linux-armv6l.tar.gz
    #    tar -xf node-v8.11.4-linux-armv6l.tar.xz || die "Couldn't extract Node"
    #    cd *6l && sudo cp -R * /usr/local/ || die "Couldn't copy Node to /usr/local"
    #else
        sudo bash -c "curl -sL https://deb.nodesource.com/setup_8.x | bash -" || die "Couldn't setup node 8" 
        sudo apt-get install -y nodejs || die "Couldn't install nodejs" 
        ## You may also need development tools to build native addons:
        ##sudo apt-get install gcc g++ make
    #fi
fi
sudo pip install -U openaps || die "Couldn't install openaps toolkit"
sudo pip install -U openaps-contrib || die "Couldn't install openaps-contrib"
sudo openaps-install-udev-rules || die "Couldn't run openaps-install-udev-rules"
sudo activate-global-python-argcomplete || die "Couldn't run activate-global-python-argcomplete"
sudo npm install -g json oref0 || die "Couldn't install json and oref0"
echo openaps installed
openaps --version
