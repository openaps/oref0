"""
process - a fake vendor to run arbitrary commands
"""

import sys, os
import shlex
from subprocess import check_output, call, PIPE
import subprocess
import json

import argparse
from plugins.vendor import Vendor
from openaps.uses.use import Use
from openaps.uses.registry import Registry

# create a usage registry/decorator
use = Registry( )
# custom registry, to track usages
get_uses = use.get_uses

def configure_add_app (app, parser):
  parser.add_argument('cmd')
  parser.add_argument('--require', action='append', default=[])
  parser.add_argument('args', nargs=argparse.REMAINDER)
  # .completer = complete_args

def set_config (args, device):
  device.add_option('cmd', args.cmd)
  device.add_option('args', ' '.join(args.args))
  device.add_option('fields', ' '.join(args.require))

def display_device (device):
  data = dict(**device.fields)
  data.update(**device.extra.fields)
  data.update(cmd=device.get('cmd'), args=device.get('args'))
  return '/{cmd:s}/{args:s}'.format(**data)

@use( )
class shell (Use):
  """ run a process in a subshell
  """
  def get_params (self, args):
    self.fields = self.device.get('fields').strip( ).split(' ')
    params = dict(remainder=getattr(args, 'remainder', [])
                , json_default=getattr(args, 'json_default', True))
    for opt in self.fields:
      if opt:
        params[opt] = getattr(args, opt)
    return params

  def prerender_json (self, data):
    """ since everything is a dict/strings/ints, we can pass thru to json
    """
    if self.json_default:
      try:
        return json.loads(data)
      except ValueError, e:
        print e
        print data
        raise

    else:
      return data
  def from_ini (self, fields):
    fields.update(json_default=fields.get('json_default', 'True') == 'True')
    if 'remainder' in fields:
      fields.update(remainder=fields.get('remainder', [ ]).strip( ).split(' '))
    return fields
  def to_ini (self, args):
    params = self.get_params(args)
    if 'remainder' in params:
      params.update(remainder=' '.join(params.get('remainder', [ ])))
    return params

  def configure_app (self, app, parser):
    parser.add_argument('--not-json-default', dest='json_default'
          , default=True, action='store_false'
          , help="When the process does not produce json.")
    self.fields = self.device.get('fields').strip( ).split(' ')
    for opt in self.fields:
      if opt:
        parser.add_argument(opt)
    parser.add_argument('remainder', nargs=argparse.REMAINDER)
  def main (self, args, app):
    # info = self.device.fields
    info = dict(**self.device.fields)
    info.update(**self.device.extra.fields)
    command = [ info.get('cmd')
              ]
    command.extend(info.get('args').split(' '))
    params = self.get_params(args)
    self.json_default = params.get('json_default')
    for opt in self.fields:
      if opt:
        command.append(getattr(args, opt))
    command.extend(getattr(args, 'remainder', []))
    command = shlex.split(' '.join(command))
    proc = subprocess.Popen(command, stdout=PIPE)
    output, stderr = proc.communicate( )
    # output = check_output(command, shell=True)
    return output

