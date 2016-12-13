#!/bin/bash

echo Run oref0-ed-battery
if /home/edison/src/EdisonVoltage/voltage json batteryVoltage battery | grep "-66" 2>/dev/null; then
    echo start Voltage server and trigger
    cd /home/edison/src/EdisonVoltage && sudo ./voltage_server &
    cd /home/edison/src/EdisonVoltage && echo 1 > /tmp/battery_trigger
fi
