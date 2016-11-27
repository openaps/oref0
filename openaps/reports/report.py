import json
from openaps.configurable import Configurable
class Report (Configurable):
  prefix = 'report'
  required = [ 'report', 'reporter', 'device', 'use' ]
  optional = [ ]
  fields = { }
  url_template = "{device:s}://{reporter:s}/{use:s}/{name:s}"
  name = None
  def __init__ (self, name=None, report=None, reporter=None, device=None, use=None, **kwds):
    self.name = report or name
    self.fields = dict(reporter=reporter, device=device, use=use, **kwds)

