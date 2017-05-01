#!/usr/bin/env python3

import logging
import argparse
import json
from flask import Flask, request
from flask_restful import Resource, Api

app = Flask(__name__)
api = Api(app)

class Notification (Resource):
    def get(self):
        print("<html><body>test</body></html>")

def run_script(args):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    else:
        logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s %(message)s')


api.add_resource(Notification, '/api/v1/notification')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Daemon for sending oref0 notifications to clients (e.g. pebble, nightscout, pushover)')
    parser.add_argument('-v', '--verbose', action="store_true", help='increase output verbosity')
    parser.add_argument('--version', action='version', version='%(prog)s 0.0.1-dev')
    app.run(host='127.0.0.1', port=5002)
    args = parser.parse_args()
    run_script(args)
