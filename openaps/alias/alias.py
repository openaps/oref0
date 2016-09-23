
from openaps.configurable import Configurable
class Alias (Configurable):
  prefix = 'alias'
  required = [ 'command' ]
  optional = [ ]
  fields = { }
  url_template = "{name:s} {command:s}"
  name = None
  def section_name (self):
    return 'alias'

  def __init__ (self, name=None, command=None, **kwds):
    self.name = name
    self.fields = dict(command=command, **kwds)

  def store  (self, config):
    if not config.has_section(self.section_name( )):
      config.add_section(self.section_name( ))
    config.set(self.section_name( ), self.name, self.fields['command'])

  def remove (self, config):
    config.remove_option(self.prefix, self.name)

  @classmethod
  def FromConfig (klass, config):
    items = [ ]
    for candidate in config.sections( ):
      if candidate.startswith(klass.prefix):
        # fields = dict(config.items(candidate))
        for name, command in config.items(candidate):
          report = klass(name=name, command=command)
          items.append(report)
    return items


