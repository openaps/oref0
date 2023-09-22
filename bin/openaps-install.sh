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

# Workaround for Jubilinux v0.2.0 (Debian Jessie) migration to LTS
if cat /etc/os-release | grep 'PRETTY_NAME="Debian GNU/Linux 8 (jessie)"' &> /dev/null; then
    # Disable valid-until check for archived Debian repos (expired certs)
    echo "Acquire::Check-Valid-Until false;" | tee -a /etc/apt/apt.conf.d/10-nocheckvalid
    # Replace apt sources.list with archive.debian.org locations
    echo -e "deb http://security.debian.org/ jessie/updates main\n#deb-src http://security.debian.org/ jessie/updates main\n\ndeb http://archive.debian.org/debian/ jessie-backports main\n#deb-src http://archive.debian.org/debian/ jessie-backports main\n\ndeb http://archive.debian.org/debian/ jessie main contrib non-free\n#deb-src http://archive.debian.org/debian/ jessie main contrib non-free" > /etc/apt/sources.list
    echo "Please consider upgrading your rig to Jubilinux 0.3.0 (Debian Stretch)!"
    echo "Jubilinux 0.2.0, based on Debian Jessie, is no longer receiving security or software updates!"
fi

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

sed -i "s/daily/hourly/g" /etc/logrotate.conf
sed -i "s/#compress/compress/g" /etc/logrotate.conf

curl -s https://raw.githubusercontent.com/openaps/oref0/$BRANCH/bin/openaps-packages.sh | bash -
mkdir -p ~/src; cd ~/src && ls -d oref0 && (cd oref0 && git checkout $BRANCH && git pull) || git clone https://github.com/openaps/oref0.git -b $BRANCH
echo "Press Enter to run oref0-setup with the current release ($BRANCH branch) of oref0,"
read -p "or press ctrl-c to cancel. " -r
cd && ~/src/oref0/bin/oref0-setup.sh
