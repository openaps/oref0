#!/bin/bash

# TODO: remove the `-o Acquire::ForceIPv4=true` once Debian's mirrors work reliably over IPv6
apt-get -o Acquire::ForceIPv4=true install -y sudo
sudo apt-get -o Acquire::ForceIPv4=true update && sudo apt-get -o Acquire::ForceIPv4=true -y upgrade
## Debian Bullseye (Raspberry Pi OS 64bit, etc) is python3 by default and does not support python2-pip.
if ! cat /etc/os-release | grep bullseye &> /dev/null; then
   sudo apt-get install -y git python python-dev software-properties-common python-numpy python-pip watchdog strace tcpdump screen acpid vim locate lm-sensors || die "Couldn't install packages"
else
   # Bullseye based OS. Get PIP2 from pypa and pip-install python packages rather than using the py3 ones from apt
   # Also, install python-is-python2, to override the distro default of linking python to python3
   sudo apt-get install -y git python-is-python2 python-dev-is-python2 software-properties-common watchdog strace tcpdump screen acpid vim locate lm-sensors || die "Couldn't install packages"
   curl https://bootstrap.pypa.io/pip/2.7/get-pip.py | python2
   python2 -m pip install numpy
fi
#sudo apt-get -o Acquire::ForceIPv4=true install -y git python python-dev software-properties-common python-numpy python-pip nodejs-legacy npm watchdog strace tcpdump screen acpid vim locate jq lm-sensors && \
sudo pip install -U openaps && \
sudo pip install -U openaps-contrib && \
sudo openaps-install-udev-rules && \
sudo activate-global-python-argcomplete && \
sudo npm install -g json oref0 && \
echo openaps installed && \
openaps --version


