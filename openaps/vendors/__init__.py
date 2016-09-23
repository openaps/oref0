
import dexcom, medtronic, process, units

from openaps.cli.subcommand import Subcommand
from openaps.cli.commandmapapp import CommandMapApp

from plugins.vendor import Vendor

class ChangeVendorApp (Subcommand):
  """
  Allow subcommand to handle setup_application
  """

def find_plugins (config):
  vendors = Vendor.FromConfig(config)
  return [ v.get_module( ) for v in vendors ]

def get_vendors ( ):
  return [ dexcom, medtronic, process, units ]

def get_map (config=None):
  vendors = all_vendors(config)
  names = [ v.__name__.split('.').pop( ) for v in vendors ]
  return dict(zip(names, vendors))

def lookup (name, config=None):
  return get_map(config)[name]

def lookup_dotted (name, config=None):
  vendors = all_vendors(config)
  names = [ v.__name__ for v in vendors ]
  return dict(zip(names, vendors))[name]


def all_vendors (config=None):
  return get_vendors( ) + find_plugins(config)

class VendorConfigurations (CommandMapApp):
  Subcommand = ChangeVendorApp
  def get_dest (self):
    return 'vendor'
  def get_commands (self):
    return all_vendors(self.parent.config)

  def get_vendor (self, vendor):
    return self.commands[vendor]

def get_configurable_devices (ctx):
  vendors = VendorConfigurations(ctx)
  return vendors


class Exported (object):
  Configurable = Vendor
  @classmethod
  def get_configurables(Klass, conf):
    return find_plugins(conf)
  @classmethod
  def get_map(Klass, conf):
    return get_map(conf)
  Command = VendorConfigurations
  Subcommand = ChangeVendorApp
