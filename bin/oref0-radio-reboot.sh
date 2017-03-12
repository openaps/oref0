radio_errors=`tail /var/log/openaps/pump-loop.log | grep "spidev5.1 already in use"`
logfile=/var/log/openaps/pump-loop.log
if [ ! -z "$radio_errors" ]; then
    if [ ! -e /run/nologin ]; then
        echo >> $logfile
        echo -n "Radio error found at " | tee -a $logfile
        date >> $logfile
        shutdown -r +5 "Rebooting to fix radio errors!" | tee -a $logfile
        echo >> $logfile
    fi
else
    if [ -e /run/nologin ]; then
        echo "No more radio errors; canceling reboot" | tee -a $logfile
        shutdown -c | tee -a $logfile
    fi
fi
