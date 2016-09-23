
import importlib
import site

from openaps.configurable import Configurable
class Vendor (Configurable):
  prefix = 'vendor'
  required = [ 'name', ]
  optional = [ ]
  fields = { }
  url_template = "{name:s}://"
  name = None
  def __init__ (self, name=None, **kwds):
    self.name = name
    self.fields = dict(**kwds)

  def get_module (self):
    site.addsitedir(self.fields.get('path'))
    return importlib.import_module(self.name)

