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

# install/upgrade to latest node 8 if neither node 8 nor node 10+ LTS are installed
if ! nodejs --version | grep -e 'v8\.' -e 'v1[02468]\.' &> /dev/null ; then
        # nodesource doesn't support armv6
        if ! arch | grep -e 'armv6' &> /dev/null ; then
            sudo bash -c "curl -sL https://deb.nodesource.com/setup_8.x | bash -" || die "Couldn't setup node 8"
            sudo apt-get install -y nodejs=8.* || die "Couldn't install nodejs"
        else
            sudo apt-get install -y nodejs npm || die "Couldn't install nodejs and npm"
            npm install npm@latest -g || die "Couldn't update npm"
        fi
        ## You may also need development tools to build native addons:
        ##sudo apt-get install gcc g++ make
fi

# upgrade setuptools to avoid "'install_requires' must be a string" error
sudo pip install setuptools -U # no need to die if this fails
sudo pip install -U openaps || die "Couldn't install openaps toolkit"
sudo pip install -U openaps-contrib || die "Couldn't install openaps-contrib"
sudo openaps-install-udev-rules || die "Couldn't run openaps-install-udev-rules"
sudo activate-global-python-argcomplete || die "Couldn't run activate-global-python-argcomplete"
sudo npm install -g json || die "Couldn't install npm json"
echo openaps installed
openaps --version
