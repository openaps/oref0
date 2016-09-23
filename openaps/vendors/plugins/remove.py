
"""
Remove vendor plugin from openaps-environment
"""

from vendor import Vendor
def main (args, app):
  for plugin in Vendor.FromConfig(app.config):
    if args.name == plugin.name:
      plugin.remove(app.config)
      app.config.save( )
      print 'removed', plugin.format_url( )
      break

