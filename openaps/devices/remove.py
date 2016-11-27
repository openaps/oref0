
"""
remove - remove a  device configuration
"""
from openaps import vendors
from openaps.devices.device import Device
import sys
def main (args, app):
  for device in Device.FromConfig(vendors, app.config):
    if args.name == device.name:
      app.config.remove_device(device)
      app.config.save( )
      print 'removed', device.format_url( )
      break

