

import add, remove, show

from openaps.cli.subcommand import Subcommand
from openaps.cli.commandmapapp import CommandMapApp

from vendor import Vendor

def get_plugins (conf):
  return Vendor.FromConfig(conf)

def get_vendor_names (conf):
  return [vendor.name for vendor in Vendor.FromConfig(conf)]

def get_vendor_map (conf):
  vendors = { }
  for vendor in Vendor.FromConfig(conf):
    vendors[vendor.name] = vendor
  return vendors

class VendorAction (Subcommand):

  def setup_application (self):
    self.vendors = get_vendor_map(self.config)
    choices = self.vendors.keys( )
    choices.sort( )
    self.parser.add_argument('name', choices=choices)
    super(VendorAction, self).setup_application( )

class VendorManagementActions (CommandMapApp):
  """ vendors - manage vendor plugin configurations """
  Subcommand = VendorAction
  name = 'command'
  title = '## Vendors Menu'
  def get_dest (self):
    return 'command'
  def get_commands (self):
    return [ add, remove, show  ]

class Exported (object):
  Configurable = Vendor
  @classmethod
  def get_configurables(Klass, conf):
    return get_plugins(conf)
  @classmethod
  def get_names(Klass, conf):
    return get_vendor_names(conf)
  @classmethod
  def get_map(Klass, conf):
    return get_vendor_map(conf)
  Command = VendorManagementActions
  Subcommand = VendorAction
