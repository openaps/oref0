#!/bin/bash

if ~/src/EdisonVoltage/voltage json batteryVoltage battery | grep "-66" 2>/dev/null; then
    cd ~/src/EdisonVoltage && sudo ./voltage_server &
	cd ~/src/EdisonVoltage && echo 1 > /tmp/battery_trigger
fi
