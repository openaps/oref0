
"""
add    - add a new report configuration
"""
from openaps import uses
from openaps.devices.device import Device
from report import Report
import reporters
import sys

def configure_app (app, parser):
  parser._actions[-1].choices = None
  reports = reporters.get_reporters( )
  parser.add_argument('reporter', choices=[r.__name__.split('.').pop( ) for r in reports])
  commands = uses.UseDeviceCommands(app.parent.devices, parent=app, config=app.parent.config)
  app.usages = commands
  commands.configure_commands(parser)
  return commands

def configure_parser (parser):
  pass

def main (args, app):
  report = Report(report=args.report, device=args.device, reporter=args.reporter, use=args.use)
  task = app.actions.selected(args).usages.commands[args.device].method.commands[report.fields['use']]
  params = task.method.to_ini(args)
  for k, v in params.items( ):
    report.add_option(k, str(v))
  report.store(app.config)
  app.config.save( )
  print "added", report.format_url( )

