#!/usr/bin/env python3

# pip3 install requests
import requests

import json
import logging
import argparse

import configparser
import sys
import re
from urllib.parse import urlsplit
import time


nightscout_host=None # will be read from ns.ini
api_secret=None # will be read from ns.ini
token_secret=None # will be read from ns.ini
token_dict={}
token_dict["exp"]=-1
auth_headers={}

def init(args):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s')

def parse_ns_ini(filename):
    global nightscout_host, api_secret, token_secret
    logging.debug("Parsing %s" % filename)
    config = configparser.ConfigParser()
    try:
        with open(filename) as f:
            config.readfp(f)
    except IOError:
        logging.error("Could not open %s" % filename)
        sys.exit(1)
    for section in config.sections():
        if section=='device "ns"':
            for option in config.options(section):
                if option=='args':
                    argsline=config.get(section, option).split(" ")
                    logging.debug("args=%s" % argsline)
                    if argsline[0]!="ns":
                        logging.error("Invalid ini file. First argument should be 'ns'")
                        sys.exit(1)
                    nightscout_host=argsline[1]
                    api_secret=argsline[2]
    if nightscout_host==None:
        logging.error("Nightscout set not found in %s'"%filename)
        sys.exit(1)
    if not api_secret.startswith('token='):
        logging.error("API_SECRET in %s should start with 'token='"%filename)
        sys.exit(1)
    p = re.compile("^token=(?P<token>[a-z0-9_]+-[a-z0-9]{16}).*")
    #p = re.compile("token=(?P<token>.*)")
    m = p.match(api_secret)
    if m:
        token_secret=m.group('token') # extra token from API_SECRET field
    else: # did not match regexp
        logging.error("Token is not valid in %s" % filename)
        sys.exit(1)


def get_nightscout_authorization_token():
    global nightscout_host, token_secret, token_dict, auth_headers
    logging.debug("get_nightscout_authorization_token")
    try:
        r = requests.get(nightscout_host+"/api/v2/authorization/request/"+token_secret)
        if r.status_code==200:
           # save authentication token to a dict
           token_dict=r.json()
           logging.debug("token_dict=%s" % token_dict)
           logging.debug("authorization valid until @%d " % token_dict['exp'])
           logging.info("Succesfully got Nightscout authorization token")
        else:
           logging.error("status_code: %d. Response: %s" % (r.status_code, r.text))
           logging.error("Could not connect to Nightscout. Please check permissions")
           sys.exit(1)
    except Exception as e:
        logging.error("Could not get_nightscout_authorization_token")
        logging.debug("Exception: %s" %e)
        sys.exit(1)


def startup_checks(args):
    parse_ns_ini(args.nsini)
    logging.info("Nightscout host: %s" % nightscout_host)
    get_nightscout_authorization_token()

def check_permissions():
    global token_dict
    pg=[]

    for perm_group in token_dict['permissionGroups']:
        pg.extend(perm_group)

    if pg==["*"]: # admin role
        logging.warning("The use of the admin role for token based authentication is not recommended, see https://openaps.readthedocs.io/en/master/docs/walkthrough/phase-1/nightscout-setup.md#switching-from-api_secret-to-token-based-authentication-for-your-rig")
    else:
        missing=[]
        for perm in ["api:treatments:read", "api:treatments:create", "api:treatments:read", "api:treatments:create", "api:devicestatus:read", "api:devicestatus:create"]:
            logging.debug("Checking %s" % perm)
            if perm not in pg:
                missing.append(perm)

        if len(missing)>0:
            logging.error("The following permissions are missing in Nightscout: %s" % missing)
            logging.error("Please follow instructions at https://openaps.readthedocs.io/en/master/docs/walkthrough/phase-1/nightscout-setup.md#switching-from-api_secret-to-token-based-authentication-for-your-rig")
            sys.exit(1)

    logging.info("All permissions in Nightscout are ok")


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description='Checks permissions in Nightscout based on your ns.ini')
        parser.add_argument('-v', '--verbose', action="store_true", help='increase output verbosity')
        parser.add_argument('--nsini', type=str, help='Path to ns.ini' , default='./ns.ini')
        args = parser.parse_args()

        init(args)
        startup_checks(args)
        check_permissions()
    except Exception:
        logging.exception("Exception in %s" % __name__)
