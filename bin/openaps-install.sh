#!/usr/bin/env bash
set -e

BRANCH=${1:-dev}
read -p "Enter your rig's new hostname (this will be your rig's "name" in the future, so make sure to write it down): " -r
myrighostname=$REPLY
echo $myrighostname > /etc/hostname
sed -r -i"" "s/localhost( jubilinux)?$/localhost $myrighostname/" /etc/hosts
sed -r -i"" "s/127.0.1.1.*$/127.0.1.1       $myrighostname/" /etc/hosts

# if passwords are old, force them to be changed at next login
passwd -S root 2>/dev/null | grep 20[01][0-6] && passwd -e root
# automatically expire edison account if its password is not changed in 3 days
passwd -S edison 2>/dev/null | grep 20[01][0-6] && passwd -e edison -i 3

# Password checking for Raspbian
if test -f /etc/os-release && grep -q Raspbian /etc/os-release && test -f /boot/issue.txt ; then
    if [[ "$(awk -F'[ -]' '/Raspberry/ {print $5"/"$6"/"$4}' /boot/issue.txt)" == "$(sudo passwd -S root|awk '{print $3}')" ]]; then 
        # Password of 'root' user has the same date as the reference build date. Change it.
        passwdPrompt=1
        echo "Please select a secure password for ssh logins to your rig (same password for multiple accounts is fine):"
        echo 'For the "root" account:'
        sudo passwd root 
    fi
    if [[ "$(awk -F'[ -]' '/Raspberry/ {print $5"/"$6"/"$4}' /boot/issue.txt)" == "$(sudo passwd -S pi|awk '{print $3}')" ]]; then 
        # Password of 'pi' user has the same date as the reference build date. Change it.
        # If we haven't already prompted with the following text, display it.
        test ${passwdPrompt:-0} -ne 1 && 
            echo "Please select a secure password for ssh logins to your rig (same password for multiple accounts is fine):"
        echo 'For the "pi" account:'
        sudo passwd pi 
    fi
    unset passwdPrompt
fi

# set timezone
dpkg-reconfigure tzdata


# TODO: remove the `-o Acquire::ForceIPv4=true` once Debian's mirrors work reliably over IPv6
apt-get -o Acquire::ForceIPv4=true update && apt-get -o Acquire::ForceIPv4=true -y dist-upgrade && apt-get -o Acquire::ForceIPv4=true -y autoremove
apt-get -o Acquire::ForceIPv4=true update && apt-get -o Acquire::ForceIPv4=true install -y sudo strace tcpdump screen acpid vim locate ntpdate ntp
#check if edison user exists before trying to add it to groups

grep "PermitRootLogin yes" /etc/ssh/sshd_config || echo "PermitRootLogin yes" >>/etc/ssh/sshd_config

if  getent passwd edison > /dev/null; then
  echo "Adding edison to sudo users"
  adduser edison sudo
  echo "Adding edison to dialout users"
  adduser edison dialout
 # else
  # echo "User edison does not exist. Apparently, you are runnning a non-edison setup."
fi

# Upgrading from Jessie/Stretch to Buster
if grep -E 'jessie|stretch' /etc/os-release > /dev/null; then
    # Add the GPG keys
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 112695A0E562B32A 54404762BBB6E853 648ACFD622F3D138 0E98404D386FA1D9 DCC9EFBF77E11517 6ED0E7B82643E131

    # Update sources.list for Buster
    echo 'deb http://deb.debian.org/debian/ buster main' > /etc/apt/sources.list
    echo '#deb-src http://deb.debian.org/debian/ buster main' >> /etc/apt/sources.list
    echo 'deb http://security.debian.org/debian-security buster/updates main' >> /etc/apt/sources.list
    echo '#deb-src http://security.debian.org/debian-security buster/updates main' >> /etc/apt/sources.list
    echo 'deb http://deb.debian.org/debian/ buster-updates main' >> /etc/apt/sources.list
    echo '#deb-src http://deb.debian.org/debian/ buster-updates main' >> /etc/apt/sources.list

    # Update and upgrade packages
    DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" && \
    DEBIAN_FRONTEND=noninteractive apt-get dist-upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

    # Clean up
    DEBIAN_FRONTEND=noninteractive apt-get autoremove -y && \
    DEBIAN_FRONTEND=noninteractive apt-get clean

    echo "System upgraded to Debian Buster."
fi


sed -i "s/daily/hourly/g" /etc/logrotate.conf
sed -i "s/#compress/compress/g" /etc/logrotate.conf

curl -s https://raw.githubusercontent.com/openaps/oref0/$BRANCH/bin/openaps-packages.sh | bash -
mkdir -p ~/src; cd ~/src && ls -d oref0 && (cd oref0 && git checkout $BRANCH && git pull) || git clone https://github.com/openaps/oref0.git -b $BRANCH
echo "Press Enter to run oref0-setup with the current release ($BRANCH branch) of oref0,"
read -p "or press ctrl-c to cancel. " -r
cd && ~/src/oref0/bin/oref0-setup.sh
