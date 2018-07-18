#!/bin/bash
set -e

read -p "Enter your rig's new hostname (this will be your rig's "name" in the future, so make sure to write it down): " -r
myrighostname=$REPLY
echo $myrighostname > /etc/hostname
sed -r -i"" "s/localhost( jubilinux)?$/localhost $myrighostname/" /etc/hosts
sed -r -i"" "s/127.0.1.1.*$/127.0.1.1       $myrighostname/" /etc/hosts

# if passwords are old, force them to be changed at next login
passwd -S edison 2>/dev/null | grep 20[01][0-6] && passwd -e root
# automatically expire edison account if its password is not changed in 3 days
passwd -S edison 2>/dev/null | grep 20[01][0-6] && passwd -e edison -i 3

if [ -e /run/sshwarn ] ; then
    echo Please select a secure password for ssh logins to your rig:
    echo 'For the "root" account:'
    passwd root
    echo 'And for the "pi" account (same password is fine):'
    passwd pi
fi

grep "PermitRootLogin yes" /etc/ssh/sshd_config || echo "PermitRootLogin yes" > /etc/ssh/sshd_config

# set timezone
dpkg-reconfigure tzdata

#dpkg -P nodejs nodejs-dev
# TODO: remove the `-o Acquire::ForceIPv4=true` once Debian's mirrors work reliably over IPv6
apt-get -o Acquire::ForceIPv4=true update && apt-get -o Acquire::ForceIPv4=true -y dist-upgrade && apt-get -o Acquire::ForceIPv4=true -y autoremove
apt-get -o Acquire::ForceIPv4=true update && apt-get -o Acquire::ForceIPv4=true install -y sudo strace tcpdump screen acpid vim python-pip locate ntpdate ntp
#check if edison user exists before trying to add it to groups

if  getent passwd edison > /dev/null; then
  echo "Adding edison to sudo users"
  adduser edison sudo
  echo "Adding edison to dialout users"
  adduser edison dialout
 # else
  # echo "User edison does not exist. Apparently, you are runnning a non-edison setup."
fi

sed -i "s/daily/hourly/g" /etc/logrotate.conf
sed -i "s/#compress/compress/g" /etc/logrotate.conf

curl -s https://raw.githubusercontent.com/openaps/oref0/master/bin/openaps-packages.sh | bash -
mkdir -p ~/src; cd ~/src && git clone git://github.com/openaps/oref0.git || (cd oref0 && git checkout master && git pull)
echo "Press Enter to run oref0-setup with the current release (master branch) of oref0,"
read -p "or press ctrl-c to cancel. " -r
cd && ~/src/oref0/bin/oref0-setup.sh
