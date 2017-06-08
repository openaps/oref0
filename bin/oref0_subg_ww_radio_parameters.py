#!/usr/bin/env python3

# This script is a wrapper for the subg ww script
# It handles a timeout in case the subg ww script hangs (otherwise it would hold the pump-loop)
# It also resets the usb if --resetusb is set (recommended for TI USB stick)
# It also issues the reset.py script of if --resetpy is set (recommand for all others)

import argparse
import configparser
import os
import sys
import logging
import subprocess
import time
import signal

PORT_NOT_SET="port not set in pump.ini"
RADIO_LOCALE_NOT_SET="radio_locale not set in pump.ini"

# get the port (device name) of the TI-chip from the pump.ini config file
def get_port_from_pump_ini(filename):
    logging.debug("Parsing %s" % filename) 
    config = configparser.ConfigParser()
    config.read(filename)
    port=PORT_NOT_SET
    radio_locale=RADIO_LOCALE_NOT_SET
    for section in config.sections():
        if section=='device "pump"':
            for option in config.options(section):
                if option=='port':
                    port=config.get(section, option)
                if option=='radio_locale':
                    radio_locale=config.get(section, option)
    if radio_locale==RADIO_LOCALE_NOT_SET:
        logging.debug("radio_locale is not set in pump.ini. Assuming US pump. No need to set WW parameters")
        sys.exit(0)
    elif str.lower(radio_locale)=='us':
        logging.debug("radio_locale is set to %s. Skipping WW-pump initialization" % radio_locale)
        sys.exit(0)    
    return port


# helper method to execute command cmd and return the returncode
# use a timeout of to, and wait w seconds after the command
def execute(cmd, cmdtimeout, wait):
    try:
        logging.debug("excuting %s" % cmd)
        proc=subprocess.Popen(cmd, shell=False)
        outs,errs=proc.communicate(timeout=cmdtimeout)
        logging.debug("script exited with %s" % proc.returncode)
        logging.debug("sleeping for %s seconds " % wait)
        time.sleep(wait)
        return proc.returncode
    except subprocess.TimeoutExpired:
        logging.error("TimeoutExpired. Killing process")
        if proc.pid:
            os.kill(int(proc.pid), signal.SIGKILL)
        logging.debug("Exit with status code 1")
        sys.exit(1)
        
def main(args):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    else:
        logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s %(message)s')

    try:
        # step 1: get port device (pump device) from pump.ini. Exit if it's a US pump
        pump_ini=os.path.join(args.dir, args.pump_ini)
        pump_port=get_port_from_pump_ini(pump_ini)
        logging.debug("Serial device (port) for pump is: %s" % pump_port)
        
        # step 2: check if port device file exists. If not reset USB if it's requested with the --resetusb parameter
        if pump_port==PORT_NOT_SET:
           logging.error("port is not set in pump.ini. Please set port to your serial device, e.g. /dev/mmeowlink")
           sys.exit(1)

        # step 3: with a TI USB stick the device/symlink can disappear for unknown reasons. Restarting the USB subsystem seems to work
        tries=0   
        while (not os.path.exists(pump_port)) and tries<2:
           logging.error("pump port %s does not exist" % pump_port)
           if args.ww_ti_usb_reset=='yes':
               exitcode=execute(["sudo", "oref0-reset-usb"], args.timeout, args.wait)
               tries=tries+1
           else: # if not --ww_ti_usb_reset==yes then quit the loop
             break

        # step 4: set environment variable
        os.environ["RFSPY_RTSCTS"]=str(args.rfsypy_rtscts)
        logging.debug("env RFSPY_RTSCTS=%s" % os.environ["RFSPY_RTSCTS"] )

        # step 5: use reset.py 
        if args.ww_ti_usb_reset=='no':
           cmd=["oref0-subg-ww-radio-parameters", str(pump_port), "--resetpy"]
           exitcode=execute(cmd, args.timeout, args.wait)

        if not os.path.exists(pump_port):
           logging.error("pump port %s does not exist. Exiting with status code 1" % pump_port)
           sys.exit(1)

        # step 6: now set the subg ww radio parameters
        exitcode=execute(['oref0-subg-ww-radio-parameters', pump_port], args.timeout, args.wait)
        sys.exit(exitcode) # propagate exit code from oref0-subg-ww-radio-parameters
    except Exception:
        logging.exception("Exception in subg_ww_radio_parameters.py")
        sys.exit(1)
      
   
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Wrapper for setting World Wide radio parameters to a Medtronic pump for TI chip')
    parser.add_argument('-d', '--dir', help='openaps dir', default='.')
    parser.add_argument('-t', '--timeout', type=int, help='timeout value for script', default=30)
    parser.add_argument('-w', '--wait', type=int, help='wait time after command', default=0.5)
    parser.add_argument('--pump_ini', help='filename for pump config file', default='pump.ini')
    parser.add_argument('--ww_ti_usb_reset', type=str, help='call oref0_reset_usb command or not. Use \'yes\' only for TI USB and WW-pump. Default: no' , default='no')
    parser.add_argument('--rfsypy_rtscts', type=int, help='sets the RFSPY_RTSCTS environment variable (set to 0 for ERF and TI USB)', default=0)
    parser.add_argument('-v', '--verbose', action="store_true", help='increase output verbosity')
    parser.add_argument('--version', action='version', version='%(prog)s 0.0.1-dev')
    args = parser.parse_args()
    if str.lower(args.ww_ti_usb_reset) not in ['', 'yes', 'no']:
       logging.fatal("Use --ww_ti_usb_reset with 'yes' or  no'. You specified %s" % args.ww_ti_usb_reset)
       sys.exit(1)
    main(args)
