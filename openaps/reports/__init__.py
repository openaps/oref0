
import add, remove, show, invoke

from openaps.cli.subcommand import Subcommand
from openaps.cli.commandmapapp import CommandMapApp

from report import Report

def get_devices (conf):
  return Report.FromConfig(conf)

def get_report_names (conf):
  return [report.name for report in Report.FromConfig(conf)]

def get_report_map (conf):
  reports = { }
  for report in Report.FromConfig(conf):
    reports[report.name] = report
  return reports

class ReportAction (Subcommand):

  def setup_application (self):

    self.reports = get_report_map(self.config)
    choices = self.reports.keys( )
    choices.sort( )
    self.parser.add_argument('report', choices=choices)
    super(ReportAction, self).setup_application( )

class ReportManagementActions (CommandMapApp):
  """ reports - manage report configurations """
  Subcommand = ReportAction
  name = 'action'
  title = '## Reports Menu'
  def get_dest (self):
    return 'action'
  def get_commands (self):
    return [ add, remove, show, invoke ]


class Exported (object):
  Configurable = Report
  @classmethod
  def get_configurables(Klass, conf):
    return get_devices(conf)
  @classmethod
  def get_names(Klass, conf):
    return get_report_names(conf)
  @classmethod
  def get_map(Klass, conf):
    return get_report_map(conf)
  Command = ReportManagementActions
  Subcommand = ReportAction
