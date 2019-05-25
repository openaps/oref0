#!/usr/bin/env bash

# This script installs mraa and ccprog for purposes of reflashing the cc1110
# chip on an Explorer Board or Explorer HAT.

if ! ldconfig -p | grep -q mraa; then # if not installed, install it
    echo Installing swig etc.
    sudo apt-get install -y libpcre3-dev git cmake python-dev swig || echo "Could not install swig etc."
    # TODO: Due to mraa bug https://github.com/intel-iot-devkit/mraa/issues/771 we were not using the master branch of mraa on dev.
    # TODO: After each oref0 release, check whether there is a new stable MRAA release that is of interest for the OpenAPS community
    MRAA_RELEASE="v1.7.0" # GitHub hash 8ddbcde84e2d146bc0f9e38504d6c89c14291480
    if [ -d "$HOME/src/mraa/" ]; then
        echo -n "$HOME/src/mraa/ already exists; "
        (echo "Updating mraa source to stable release ${MRAA_RELEASE}" && cd $HOME/src/mraa && git fetch && git checkout ${MRAA_RELEASE} && git pull) || echo "Couldn't pull latest mraa ${MRAA_RELEASE} release"
    else
        echo -n "Cloning mraa "
        (echo -n "stable release ${MRAA_RELEASE}. " && cd $HOME/src && git clone -b ${MRAA_RELEASE} https://github.com/intel-iot-devkit/mraa.git) || echo "Couldn't clone mraa release ${MRAA_RELEASE}"
    fi
    # build mraa from source
    ( cd $HOME/src/ && mkdir -p mraa/build && cd $_ && cmake .. -DBUILDSWIGNODE=OFF && \
    make && sudo make install && echo && touch /tmp/reboot-required && echo mraa installed. Please reboot before using. && echo ) || echo "Could not compile mraa"
    sudo bash -c "grep -q i386-linux-gnu /etc/ld.so.conf || echo /usr/local/lib/i386-linux-gnu/ >> /etc/ld.so.conf && ldconfig" || echo "Could not update /etc/ld.so.conf"
fi

mkdir -p ~/src
if [ -d "$HOME/src/ccprog/" ]; then
    echo "$HOME/src/ccprog/ already exists; updating"
    cd $HOME/src/ccprog/ && git pull || echo "Could not git pull ccprog"
else
    cd ~/src && git clone https://github.com/ps2/ccprog.git || echo "Could not clone ccprog"
fi
cd $HOME/src/ccprog/ && make ccprog || echo "Could not make ccprog"
