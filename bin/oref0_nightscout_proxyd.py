#!/usr/bin/env python3

# pip3 install requests
import requests

import json
import logging
import argparse
from flask import Flask, request
from flask_restful import Resource, Api
from flask import request as flaskrequest

import configparser
import sys
import re
from urllib.parse import urlsplit
import time


app = Flask(__name__)
api = Api(app)

nightscout_host=None # will be read from ns.ini
api_secret=None # will be read from ns.ini
token_secret=None # will be read from ns.ini
token_dict={}
token_dict["exp"]=-1
auth_headers={}
THREE_MINUTES=3*60

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

def maybe_refresh_authorization_token():
    global token_dict
    logging.debug("Checking if authentication token is still valid")
    if time.time()>token_dict['exp']-THREE_MINUTES:
       refresh_authorization_token()
       

def refresh_authorization_token():
    global nightscout_host, token_secret, token_dict, auth_headers
    logging.debug("refresh_authorization_token") 
    try:
        r = requests.get(nightscout_host+"/api/v2/authorization/request/"+token_secret)
        if r.status_code==200:
           # save authentication token to a dict
           token_dict=r.json()
           #auth_headers["Authorization"]="Bearer %s" % token_dict['token'] 
           logging.debug("authorization valid until @%d " % token_dict['exp'])
           logging.info("Refreshed Nightscout authorization token")
        else:
           logging.debug("status_code: %d. Response: %s" % (r.status_code, r.text))
    except Exception as e:
        logging.error("Could not refresh_authorization_token")
        logging.debug("Exception: %s" %e) 
    
    
def startup_checks(args):
    
    parse_ns_ini(args.nsini)
    logging.info("Nightscout host: %s" % nightscout_host)
    refresh_authorization_token()

def check_permissions():
    global token_dict
    missing=[]
    for perm in [["api:treatments:read"], ["api:treatments:create"]]:
        if perm not in token_dict['permissionGroups']:
          missing.append(perm)

    if len(missing)>0:
       logging.error("The following permissions are missing in Nightscout: %s" % missing)
       sys.exit(1)
    logging.info("All permissions Nightscout permissions are ok")
    
class NightscoutProxyBase(Resource):
    def get(self):
        global auth_headers
        logging.debug(auth_headers)
        logging.debug("GET %s" % flaskrequest.full_path)
        maybe_refresh_authorization_token()
        r=requests.get(nightscout_host+flaskrequest.full_path, headers=auth_headers)
        logging.debug("StatusCode=%d Response=%s" % (r.status_code, r.text))
        statuscodeclass=int(r.status_code)/100
        if statuscodeclass==2:
            return r.text, 200
        elif statuscodeclass==4:
            return "4xx error", r.status_code
        elif statuscodeclass==5:
            return "5xx error", r.status_code

    def post(self):# NOT IMPLEMENTED YET
        logging.debug("POST %s" % full_path)
        return "ok", 200
    def put(self): # NOT IMPLEMENTED YET
        logging.debug("PUT %s" % full_path)
        return "ok", 200
  # Get JSON data
  #json_data = request.get_json(force=True)

class NightscoutProxyEntries(NightscoutProxyBase):
    pass

class NightscoutProxyEntriesSgv(NightscoutProxyBase):
    pass


class NightscoutProxyTreatments(NightscoutProxyBase):
    pass
        
api.add_resource(NightscoutProxyEntries, '/api/v1/entries.json')
api.add_resource(NightscoutProxyEntriesSgv, '/api/v1/entries/sgv.json')
api.add_resource(NightscoutProxyTreatments, '/api/v1/treatments.json')


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description='Initializes the connection between the openaps environment and the insulin pump. It can reset_spi_serial and it will initalize the connetion to the World Wide pumps if necessary')
        parser.add_argument('-v', '--verbose', action="store_true", help='increase output verbosity')
        parser.add_argument('-check', '--check', action="store_true", help="check permission and don't start server", default=False)
        parser.add_argument('--debug', action="store_true", help='debug mode for flask', default=False)
        parser.add_argument('--bind', type=str, help='IP address to bind to' , default='127.0.0.1')
        parser.add_argument('--port', type=int, help='Port to bind to' , default='1338')
        parser.add_argument('--nsini', type=str, help='Path to ns.ini' , default='./ns.ini')
        args = parser.parse_args()
        
        init(args)
        startup_checks(args)
        if args.check:
           check_permissions()
        else: # start in server mode
           app.run(host=args.bind, port=args.port, debug=args.debug)
    except Exception:
        logging.exception("Exception in %s" % __name__)
