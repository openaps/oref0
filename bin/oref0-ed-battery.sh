#!/bin/bash

if ~/src/EdisonVoltage/voltage json batteryVoltage battery | grep "-66" 2>/dev/null; then
    echo start Voltage server and trigger
    cd /home/src/EdisonVoltage && sudo ./voltage_server &
    cd /home/src/EdisonVoltage && echo 1 > /tmp/battery_trigger
fi
