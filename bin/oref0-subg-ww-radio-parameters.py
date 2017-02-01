#!/usr/bin/env python3

# This script is a wrapper for the subg ww script
# It handles a timeout in case the subg ww script hangs (otherwise it would hold the pump-loop)
# And it also resets the usb if --resetusb is set (recommended for TI USB stick)

import argparse
import configparser
import os
import sys
import logging
import subprocess
import time

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
       logging.error("radio_locale is not set in pump.ini. Please set radio_locale=WW in your pump.ini")
    return port
        
def run_script(args):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    else:
        logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s %(message)s')

    try:
        # step 1: get port device (pump device) from pump.ini
        pump_ini=os.path.join(args.dir, args.pump_ini)
        pump_port=get_port_from_pump_ini(pump_ini)
        
        # step 2: check if port device file exists. If not reset USB if it's requested with the --resetusb parameter
        if pump_port==PORT_NOT_SET:
           logging.error("port is not set in pump.ini. Please set port to your serial device, e.g. /dev/mmeowlink")
           sys.exit(1)

        tries=0   
        while (not os.path.exists(pump_port)) and tries<2:
           logging.error("pump port %s does not exist" % pump_port)
           if args.resetusb:
               logging.debug("running oref-reset-usb script to recover TI USB stick")
               exitcode=subprocess.call("sudo oref0-reset-usb", shell=True, timeout=args.timeout)
               logging.debug("script exited with %s" % exitcode)
               logging.debug("sleeping for %s seconds " % args.wait)
               time.sleep(args.wait)
               tries=tries+1
           else: # if not --resetusb then quit the loop
             break

        if not os.path.exists(pump_port):
           logging.error("pump port %s does not exist. Exiting with status code 1" % pump_port")
           sys.exit(1)


        # step 3: set environment variables
        os.environ["RFSPY_RTSCTS"]=str(args.rfsypy_rtscts)
        logging.debug("env RFSPY_RTSCTS=%s" % os.environ["RFSPY_RTSCTS"] )
        os.environ["SERIAL_PORT"]=pump_port
        logging.debug("env SERIAL_PORT=%s" % pump_port)

        # step 4: call the main script and wait for a timeout
        exitcode=subprocess.call("oref0-subg-ww-radio-parameters", shell=False, timeout=args.timeout)
        logging.debug("script exited with %s" % exitcode)
        
    except subprocess.TimeoutExpired:
        logging.error("TimeoutExpired. Killing process")
        proc.kill()
        sys.exit(1)
    except Exception as ex:
        logging.error("Exception: %s" % str(ex))
        sys.exit(1)
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Wrapper for setting World Wide radio parameters to a Medtronic pump for TI chip')
    parser.add_argument('-d', '--dir', help='openaps dir', default='.')
    parser.add_argument('-t', '--timeout', type=int, help='timeout value for script', default=30)
    parser.add_argument('-w', '--wait', type=int, help='wait time after command', default=60)
    parser.add_argument('--pump_ini', help='filename for pump config file', default='pump.ini')
    #parser.add_argument('--resetpy', action="store_true", help='use reset.py script from subg_rfspy', default=True)
    parser.add_argument('--resetusb', action="store_true", help='call oref0_reset_usb command if serial pump device is not found', default=False)
    parser.add_argument('--rfsypy_rtscts', type=int, help='sets the RFSPY_RTSCTS environment variable (set to 0 for ERF and TI USB)', default=0)
    parser.add_argument('-v', '--verbose', action="store_true", help='increase output verbosity')
    parser.add_argument('--version', action='version', version='%(prog)s 0.0.1-dev')
    args = parser.parse_args()
    run_script(args)
