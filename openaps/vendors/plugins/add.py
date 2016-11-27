
"""
Add a new vendor plugin to openaps-environment.
"""

from vendor import Vendor

def configure_app (app, parser):
  parser._actions[-1].choices = None
  parser.add_argument('--path',  default='.'
                     , help="Path to module's namespace")

def main (args, app):
  vendor = Vendor(args.name, path=args.path)
  try:
    module = vendor.get_module( )
    vendor.add_option('module', module.__name__)
    vendor.store(app.config)
    app.config.save( )
    print "added", vendor.format_url( )
  except (ImportError), e:
    print e
    print """{name:s} doesn't seem to be an importable python module
If it is a python module, try using --path to influence
PYTHONPATH
      """.format(name=args.name)

