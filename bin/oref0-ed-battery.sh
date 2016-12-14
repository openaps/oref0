#!/bin/bash

echo Run oref0-ed-battery
if ! /home/edison/src/EdisonVoltage/voltage json batteryVoltage battery | grep "-66" 2>/dev/null; then
    echo start Voltage
    sudo /home/edison/src/EdisonVoltage/voltage
fi
