
"""
add   - add an alias
"""

from alias import Alias

def configure_app (app, parser):
  parser._actions[-1].choices = None
  parser.add_argument('command',  help='The command to alias.')

def main (args, app):
  new_alias = Alias(name=args.name, command=args.command)
  new_alias.store(app.config)
  app.config.save( )
  print "added", new_alias.format_url( )

