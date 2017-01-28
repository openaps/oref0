#!/bin/bash

# This script returns the device name that is set in the pump.ini config file
# returns 0 in case device name exists
# returns -1 if the device name does not exist, or the program is not started from the openaps dir

# pump config file
PUMP="pump.ini"

# check if pump.ini exists
if [[ ! -f "${PUMP}" ]]; then
   echo "Error: Not an openaps dir. Could not find $PUMP in `pwd`"
   exit -1
fi

# get the port mentioned in the pump.ini
PORT=`grep port pump.ini | grep -v "^#" | sed -e 's/.*port.*=\(.*\)$/\1/g' | tr -d '[:blank:]'`

echo $PORT
if [[ ! -c "${PORT}" ]]; then # device exists and is a character device
  exit 0
else
   exit -1
fi