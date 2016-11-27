
from openaps.cli.subcommand import Subcommand
from openaps.cli.commandmapapp import CommandMapApp

def no_uses (device, config):
  return [ ]

def known_uses (config, device):
  return getattr(device.vendor, 'get_uses', no_uses)(device, config)

def plugin_uses (config, device):
  return [ ]

def all_uses (config, device):
  return known_uses(config, device) + plugin_uses(config, device)

class DeviceUsageTask (Subcommand):
  """ One use
  """
  def __init__ (self, method=None, parent=None):
    self.usage = method
    self.name = method.__name__.split('.').pop( )
    self.method = method(parent.device, parent)
    self.parent = parent
  def setup_application (self):
    self.method.parser = self.parser
    super(DeviceUsageTask, self).setup_application( )
    # self.method.setup_application( )
    # self.configure_parser(self.parser)
  def __call__ (self, args, app):
    return self.method(args, app)


class DeviceUsageMap (CommandMapApp):
  """ Map of uses for specific device
  """
  Subcommand = DeviceUsageTask
  def get_dest (self):
    return 'use'
  def __init__ (self, device=None, parent=None):
    self.device = device
    self.usages = all_uses(parent.parent.config, device)
    super(DeviceUsageMap, self).__init__(parent)

  def get_help (self):
    return """Usage Details"""
  def get_title (self):
    return getattr(self, 'title', '## Device %s' % self.device.name)
  def get_metavar (self):
    return 'USAGE'

  def get_description (self):
    template = """\
vendor {vendor:s}
{docs:s}
    """
    kwargs = dict( name=self.device.name
                 , docs=self.device.vendor.__doc__
                 , vendor=self.device.vendor.__name__
                 , usages=', '.join([u.__name__ for u in self.usages]))
    return template.format(**kwargs)

  def get_commands (self):
    return self.usages

# TODO: rename KnownDeviceUsages
class UseDeviceTask (Subcommand):
  """ Manage device usage

  Per vendor usage tasks for a device.
  """
  def __init__ (self, method=None, parent=None):
    super(UseDeviceTask, self).__init__(method=method.vendor, parent=parent)
    self.device = method
    self.method = DeviceUsageMap(self.device, self)
    # self.method = method
    # self.method = method.vendor
    self.name = method.name

  def get_help (self):
    return ''.join(self.device.vendor.__doc__.split("\n\n")[:1])
  def get_description (self):
    return None
    # return ''.join(self.device.vendor.__doc__.split("\n\n")[:])

  def setup_application (self):
    name = 'configure_%s_app' % self.parent.name
    getattr(self.method, 'configure_app', self._no_op_setup)(self, self.parser)
    getattr(self.method, name, self._no_op_setup)(self, self.parser)
    self.method.configure_commands(self.parser)
  def __call__ (self, args, app):
    return self.method.selected(args)(args, app)

# TODO: rename KnownDeviceCommandMap
class UseDeviceCommands (CommandMapApp):
  """ device - which device to use """
  Subcommand = UseDeviceTask
  metavar = 'device'
  def __init__ (self, devices=None, parent=None, config=None):
    self.devices = devices
    self.config = config
    if parent and getattr(parent, 'config', config) is None:
      self.config = parent.config
    super(UseDeviceCommands, self).__init__(parent)
  def get_title (self):
    return 'Known Devices Menu'
  def get_description (self):
    return """\
These are the devices openaps knows about:\
    """
  def get_dest (self):
    return 'device'
  def get_help (self):
    return """Name and description:"""
  def get_commands (self):
    choices = self.devices.keys( )
    choices.sort( )
    return [ self.devices[choice] for choice in choices ]

def get_uses_for (device, parent=None):
  return all_uses(parent.config, device)

