from openaps.config import Config
import json

def install_show_arguments (parser):

  parser.add_argument('--ini', dest='format', action='store_const', const=format_ini, default=format_url)
  parser.add_argument('--json', dest='format', action='store_const', const=format_json)

def format_json (report):
  info = { 'name': report.name, report.name: report.fields, 'type': report.prefix }
  if hasattr(report, 'extra'):
    info['extra'] = report.extra.fields
  return json.dumps(info)

def format_ini (report):
  config = Config( )
  config.add_device(report)

  if hasattr(report, 'extra'):
    for k, v in report.extra.fields.items( ):
      config.set(report.section_name( ), k, v)
  return config.fmt( )

def format_url (report):
  return report.format_url( )

