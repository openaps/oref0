import json
class Configurable (object):
  name = None
  required = [ ]
  optional = [ ]
  prefix = '{name:s}'
  url_template = ""
  def __init__ (self, name, **kwargs):
    self.name = name
    self.fields = kwargs

  def section_name (self):
    return '%s "%s"' % (self.prefix, self.name)

  def add_option (self, k, v):
    self.fields[k] = v
    if k not in self.required + self.optional:
      self.optional.append(k)

  def get (self, k, *args):
    return self.fields.get(k, *args)
  def items (self):
    return self.fields.items( )

  def format_url (self):
    return self.url_template.format(name=self.name, **self.fields)

  def store  (self, config):
    if not config.has_section(self.section_name( )):
      config.add_device(self)
    else:
      for k, v in self.items( ):
        config.set(self.section_name( ), k, v)

  def remove (self, config):
    config.remove_device(self)

  @classmethod
  def FromImport (klass, candidate, config=None):
    name = candidate.get('name')
    fields = candidate.get(name)
    inst = klass(name, **fields)
    return inst
  @classmethod
  def FromConfig (klass, config):
    items = [ ]
    for candidate in config.sections( ):
      if candidate.startswith(klass.prefix):
        name = json.loads(candidate.split(' ').pop( ))
        # for f in klass.required:
        fields = dict(config.items(candidate))
        report = klass(name=name, **fields)
        items.append(report)
    return items


