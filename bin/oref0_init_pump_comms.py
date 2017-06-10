#!/usr/bin/env python3

# This script initializes the connection between the openaps environment
# and the insulin pump
# Currently supported features:
# - Call reset function for spi_serial
# - Initialize WW pumps

import sys
import logging
import argparse

def run_script(args):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    else:
        logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s %(message)s')
    if args.reset_spi_serial=='yes':
        init_spi_serial()
    if args.init_ww in ['yes', 'auto']:
        init_ww_pump(args)
    
    logging.debug("Exit succesfully with exit code 0")
    sys.exit(0)

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
    except ImportError: # silence import error by default
        logging.debug("spi_serial not installed. Assuming not using spidev")
    except Exception: 
        logging.exception("Exception in oref0-init-pump-comms spi_serial")
        sys.exit(1)

def init_ww_pump(args):
    # iniialize ww pump connection (if it's used)
    try:
        logging.debug("Import oref0_subg_ww_radio_parameters")
        import oref0_subg_ww_radio_parameters
        oref0_subg_ww_radio_parameters.main(args)
    except ImportError: 
        logging.debug("Could not import oref0_subg_ww_radio_parameters. Assuming US pump. This is no error")
    except Exception:
        logging.exception("Exception in oref0-init-pump-comms init_ww_pump:")
        sys.exit(1)

def listen_for_silence(args):        
    

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description='Initializes the connection between the openaps environment and the insulin pump. It can reset_spi_serial and it will initalize the connetion to the World Wide pumps if necessary')
        # default arguments
        parser.add_argument('-v', '--verbose', action="store_true", help='increase output verbosity')
        parser.add_argument('--version', action='version', version='%(prog)s 0.0.1-dev')
        # arguments required for ww pump
        parser.add_argument('--dir', help='openaps dir', default='.')
        parser.add_argument('--timeout', type=int, help='timeout value for script', default=50)
        parser.add_argument('--wait', type=int, help='wait time after each command', default=1)
        parser.add_argument('--pump_ini', help='filename for pump config file', default='pump.ini')
        parser.add_argument('--ww_ti_usb_reset', type=str, help='call oref0_reset_usb command or not. Use \'yes\' only for TI USB and WW-pump. Default: no' , default='no')
        parser.add_argument('--rfsypy_rtscts', type=int, help='sets the RFSPY_RTSCTS environment variable (set to 0 for ERF and TI USB)', default=0)
        parser.add_argument('--reset_spi_serial', type=str help='init spi serial on explorer board', default='yes')
        parser.add_argument('--init_ww', type=str, help='init world wide pump, yes/no/auto', default='auto')
        parser.add_argument('--mmtune', type=str, help='run mmtune', default='no')
        parser.add_argument('--listen_for_silence', type=str, help='listen for silence before mmtune', default='yes')
        args = parser.parse_args()
        run_script(args)
    except Exception:
        logging.exception("Exception in oref0_init_pump_comms.py")

