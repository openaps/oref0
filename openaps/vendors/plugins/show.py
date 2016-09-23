
"""
Show/list vendor plugins

"""

from openaps.cli import helpers
from vendor import Vendor

def configure_app (app, parser):
  parser.set_defaults(name='*')
  parser._actions[-1].nargs = '?'
  parser._actions[-1].choices.append('*')
  helpers.install_show_arguments(parser)

def main (args, app):
  for plugin in Vendor.FromConfig(app.config):
    if args.name in [ '*', plugin.name ]:
      print args.format(plugin)

