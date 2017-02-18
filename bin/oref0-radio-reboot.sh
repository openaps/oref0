radio_errors=`tail /var/log/openaps/pump-loop.log | grep "spidev5.1 already in use"`
if [ ! -z "$radio_errors" ]
then
  logfile=~/reset-log.txt
  date >> $logfile
  echo "Radio error found" | tee -a $logfile
  wall "Rebooting to fix radio errors!"
  reboot | tee -a $logfile
fi

