#!/bin/bash

echo "Starting MRAA build...Installing dependencies..."
sudo apt-get -y install git build-essential swig3.0 cmake libjson-c-dev
echo "Downloading MRAA..."
mkdir -p ~/src && cd ~/src && wget https://github.com/intel-iot-devkit/mraa/archive/v1.7.0.tar.gz
echo "Extracting and building MRAA..."
tar -xvf v1.7.0.tar.gz && mv mraa-1.7.0/ mraa/
mkdir -p mraa/build && cd mraa/build && cmake .. -DBUILDSWIGNODE=OFF -DCMAKE_INSTALL_PREFIX:PATH=/usr && make && sudo make install
echo "Running ldconfig..."
bash -c "grep -q i386-linux-gnu /etc/ld.so.conf || echo /usr/local/lib/i386-linux-gnu/ >> /etc/ld.so.conf && ldconfig"
echo "MRAA installed. Please reboot before using."

mkdir -p ~/src
if [ -d "$HOME/src/ccprog/" ]; then
    echo "$HOME/src/ccprog/ already exists; updating"
    cd $HOME/src/ccprog/ && git pull || echo "Could not git pull ccprog"
else
    cd ~/src && git clone https://github.com/ps2/ccprog.git || echo "Could not clone ccprog"
fi
cd $HOME/src/ccprog/ && make ccprog || echo "Could not make ccprog"
