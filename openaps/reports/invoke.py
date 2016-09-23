
"""
invoke   - generate a report
"""
from __future__ import print_function
from openaps.reports.report import Report
from openaps import uses
import reporters
import sys
import argparse

def configure_app (app, parser):
  """
  """
  parser._actions[-1].nargs = '+'

def main (args, app):
  # print args.report
  # print app.parser.parse_known_args( )
  requested = args.report[:]
  for spec in requested:
    report =  app.actions.selected(args).reports[spec]
    device = app.devices[report.fields['device']]
    task = app.actions.commands['add'].usages.commands[device.name].method.commands[report.fields['use']]
    # print(task.name, task.usage, task.method, report.fields, app.inputs)
    # print device.name, device
    # print report.name, report.fields
    # XXX.bewest: very crude, need to prime the Use's args from the config
    app.parser.set_defaults(**task.method.from_ini(report.fields))
    args, extra = app.parser.parse_known_args(app.inputs)
    """
    for k, v in report.fields.items( ):
      setattr(args, k, v)
    """
    # print args
    print(report.format_url( ))
    repo = app.git_repo( )

    try:
        output = task.method(args, app)
    except Exception as e:
        print(report.name, ' raised ', e, file=sys.stderr)
        # save prior progress in git
        app.epilog( )
        # ensure we still blow up with non-zero exit
        raise
    else:
        reporters.Reporter(report, device, task)(output)
        print('reporting', report.name)
        repo.git.add([report.name], write_extension_data=False)
        # XXX: https://github.com/gitpython-developers/GitPython/issues/265o
        # GitPython <  0.3.7, this can corrupt the index
        # repo.index.add([report.name])
