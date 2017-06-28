#!/usr/bin/env python

# This script initializes the connection between the openaps environment
# and the insulin pump
# Currently supported features:
# - Call reset function for spi_serial
# - Initialize WW pumps
# - Listen for silence (mmeowlink-any-pump-comms.py ) 

import sys
import logging
import argparse
import ConfigParser
import os
import sys
import subprocess
import time
import signal
import json

from mmeowlink.cli.any_pump_comms_app import AnyPumpCommsApp
from mmeowlink.cli.mmtune_app import MMTuneApp
from mmeowlink.vendors.serial_interface import AlreadyInUseException 

PORT_NOT_SET="port not set in pump.ini"
RADIO_LOCALE_NOT_SET="radio_locale not set in pump.ini"
RADIO_TYPE_NOT_SET="radio_type not set in pump.ini"

# get the port (device name) of the TI-chip from the pump.ini config file
# get the radio_locale of the users pump from the pump.ini config file (WW = World Wide)
# get the radio_type of the users pump from the pump.ini config file
# Question/TODO: is radio_type = mmcommander still used?
def get_port_and_radio_locale_from_pump_ini(filename, args):
    logging.debug("Parsing %s" % filename) 
    config = ConfigParser.ConfigParser()
    config.read(filename)
    args.port=PORT_NOT_SET
    args.radio_locale=RADIO_LOCALE_NOT_SET
    args.radio_type=RADIO_TYPE_NOT_SET
    # parse the pump.ini file for section in config.sections():
    for section in config.sections():
        if section=='device "pump"':
            for option in config.options(section):
                if option=='port':
                    args.port=config.get(section, option)
                if option=='radio_locale':
                    args.radio_locale=str.upper(config.get(section, option))
                if option=='radio_type':
                    args.radio_type=config.get(section, option)

    if args.radio_locale==RADIO_LOCALE_NOT_SET:
        logging.debug("radio_locale is not set in pump.ini. Assuming US pump. No need to init world wide pump")
        args.radio_locale="US"
    logging.debug("port=%s, radio_locale=%s, radio_typoe=%s" % (args.port, args.radio_locale, args.radio_type))
    args.serial=None
    args.ignore_wake=None
    return args

def init_spi_serial():
    # invoke same command's as reset_spi_serial.py
    # https://github.com/scottleibrand/spi_serial/blob/master/scripts/reset_spi_serial.py
    # this will reset the spi serial connection (if it's used)
    try:
        logging.debug("Import spi_serial")
        import spi_serial
        logging.debug("Opening spidev serial connection")
        s = spi_serial.SpiSerial()
        logging.debug("Issuing spidev serial reset")
        s.reset()
        logging.debug("spi_serial reset done")
    except ImportError: # silence import error by default
        logging.debug("spi_serial not installed. Assuming not using spidev")
    except Exception: 
        logging.exception("Exception in oref0-init-pump-comms spi_serial")
        sys.exit(1)

def init_ww_pump(args):
    # initialize ww pump connection (if it's used)
    try:
        logging.debug("Import oref0_subg_ww_radio_parameters")
        import oref0_subg_ww_radio_parameters
        oref0_subg_ww_radio_parameters.main(args)
    #except ImportError: 
    #    logging.debug("Could not import oref0_subg_ww_radio_parameters. Assuming US pump. This is no error")
    except Exception:
        logging.exception("Exception in oref0_init_pump_comms.py init_ww_pump:")
        sys.exit(1)


def wait_for_silence(args):        
# https://github.com/scottleibrand/mmeowlink/blob/master/bin/mmeowlink-any-pump-comms.py
    if args.wait_for==1:
        logging.info("Listening for %d second of silence" % args.wait_for)
    else:
        logging.info("Listening for %d seconds of silence" % args.wait_for)
        
    startTime=currentTime=time.time()
    silenceDetected=False
    loop=0
    while (currentTime-startTime<args.wait_for) or silenceDetected:
        loop=loop+1
        currentTime=time.time()
        logging.debug("Listen for silence loop %d / %.1f sec." % (loop, currentTime-startTime))
        app=AnyPumpCommsApp()
        app.run(args)
        # app.run doesn't return the call status, so we need to interrogate the object:
        if app.app_result == 0:
            logging.debug("No comms detected")
            silenceDetected=True
        else:
            logging.debug("Comms with pump detected")
    return silenceDetected


def main(args):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    else:
        logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s %(message)s')

    try:
        # parse pump.ini for port, radio_locale and radio_type and store them in args
        args=get_port_and_radio_locale_from_pump_ini(args.pump_ini, args)
            
        if args.reset_spi_serial=='yes' or (args.reset_spi_serial=='auto' and args.port=='/dev/spidev5.1'):
            init_spi_serial()
            
        if args.init_ww == 'yes' or (args.init_ww=='auto' and args.radio_locale=='WW'):
            init_ww_pump(args)

        if args.wait_for>0:
            silenceDetected=wait_for_silence(args)
            if silenceDetected:
                logging.info("No commms detected")
            else:
                logging.info("Comms with pump detected")
                sys.exit(1)
       
        logging.debug("Exit succesfully with exit code 0")
        sys.exit(0)
    except AlreadyInUseException as e:
        logging.exception(e)
        sys.exit(1)
       
    


#class MMTuneAppForOref0(MMTuneApp):
#    def main(self, args):
#        tuner = MMTune(self.link, args.serial, args.radio_locale)
#        output = tuner.run()
#       #print json.dumps(output, sort_keys=True,indent=4, separators=(',', ': '))
    
if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description='Initializes the connection between the openaps environment and the insulin pump. It can reset_spi_serial and it will initalize the connetion to the World Wide pumps if necessary')
        # default arguments
        parser.add_argument('-v', '--verbose', action="store_true", help='increase output verbosity')
        parser.add_argument('--version', action='version', version='%(prog)s 0.0.1-dev')
        # arguments required for ww pump
        parser.add_argument('--dir', help='openaps dir', default='.')
        parser.add_argument('--timeout', type=int, help='timeout value for script', default=50)
        parser.add_argument('--wait_for', type=int, help='wait time silence', default=-1)
        parser.add_argument('--wait-after-cmd', type=int, help='wait time after each command', default=1)
        parser.add_argument('--pump_ini', help='filename for pump config file', default='pump.ini')
        parser.add_argument('--ww_ti_usb_reset', type=str, help='call oref0_reset_usb command or not. Use \'yes\' only for TI USB and WW-pump. Default: no' , default='no')
        parser.add_argument('--rfsypy_rtscts', type=int, help='sets the RFSPY_RTSCTS environment variable (set to 0 for ERF and TI USB)', default=0)
        parser.add_argument('--reset_spi_serial', type=str, help='init spi serial on explorer board, yes/no/auto', default='auto')
        parser.add_argument('--init_ww', type=str, help='init world wide pump, yes/no/auto', default='auto')
        parser.add_argument('--mmtune', type=str, help='run mmtune', default='no')
        parser.add_argument('--listen_for_silence', type=str, help='listen for silence before mmtune', default='yes')
        args = parser.parse_args()
        main(args)
    except Exception:
        logging.exception("Exception in oref0_init_pump_comms.py")

