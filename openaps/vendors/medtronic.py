
"""
Medtronic - openaps driver for Medtronic
"""
from openaps.uses.use import Use
from openaps.uses.registry import Registry
from openaps.configurable import Configurable
from openaps.glucose.convert import Convert as GlucoseConvert
import decocare
import argparse
import json
from decocare import stick, session, link, commands, history
from datetime import datetime
from dateutil import relativedelta
from dateutil.parser import parse

def configure_use_app (app, parser):
  pass
  # parser.add_argument('foobar', help="LOOK AT ME")

def configure_add_app (app, parser):
  parser.add_argument('serial', nargs='?', default='')

def configure_app (app, parser):
  if app.parent.name == 'add':
    """
    print "CONFIG INNER", app, app.parent.name, app.name
    """
def configure_parser (parser):
  pass
def main (args, app):
  """
  print "MEDTRONIC", args, app
  print "app commands", app.selected.name
  """


use = Registry( )

@use( )
class scan (Use):
  """ scan for usb stick """
  def configure_app (self, app, parser):
    pass
    # print "hahaha"
  def scanner (self):
    from decocare.scan import scan
    return scan( )
  def main (self, args, app):
    return self.scanner( )

import logging
import logging.handlers
class MedtronicTask (scan):
  MAX_SESSION_DURATION = 10
  requires_session = True
  save_session = True
  record_stats = True

  def before_main (self, args, app):
    self.setup_medtronic( )
    if self.requires_session:
      self.check_session(app)
    else:
      self.pump.setModel(number=self.device.get('model', ''))
    self.save_session = self.requires_session

  def after_main (self, args, app):
    if self.save_session:
      self.write_session_file(self.update_session_info(self.session))

    if self.uart:
      self.uart.close( )

  def write_session_file (self, session):
    with open(self.device.get('session', '{0}-session.json'.format(self.device.name)), 'w+') as io:
      json.dump(session, io)

  def read_session_file (self):
    session = dict( )
    with open(self.device.get('session', '{0}-session.json'.format(self.device.name)), 'a+') as io:
      try:
        session = json.load(io)
      except (ValueError), e:
        pass
    return session

  def get_session_info (self):

    session = self.read_session_file( )

    expires = session.get('expires', None)

    if expires is not None:
      expires = parse(expires)

    now = datetime.now( )
    out = dict(device=self.device.name
      , vendor=__name__
      , used=now
      )
    if expires is None or expires < now or (expires - now).total_seconds() > (60 * self.MAX_SESSION_DURATION):
      fields = self.create_session( )
      out.update(**fields)

    else:
      out['expires'] = expires

      out['model'] = session.get('model', self.device.get('model', None))
    session.update(**out)
    return session


  def update_session_info (self, fields):
    out = { }
    uses_extra = self.device.get('extra', None)
    config = self.device
    if uses_extra:
      config = self.device.extra

    out['expires'] = fields['expires'].isoformat( )
    out['model'] = fields['model']
    return out

  def create_session (self):
    minutes = int(self.device.get('minutes', 3))
    now = datetime.now( )
    self.pump.power_control(minutes=minutes)
    model = self.get_model( )
    offset = relativedelta.relativedelta(minutes=minutes) + relativedelta.relativedelta(minutes=-1)
    out = dict(device=self.device.name
      , model=model
      , vendor=__name__
      , created_at=now
      , started=now
      , expires=now + offset
      )
    return out
  def check_session (self, app):
    self.session = self.get_session_info( )
    model = self.session.get('model', None)

    if model is None:
      model = self.get_model( )
      self.session.update(model=model)
    self.pump.setModel(number=model)

  def get_model (self):
    model = self.pump.read_model( ).getData( )
    return model
  def setup_medtronic (self):
    log = logging.getLogger(decocare.__name__)
    level = getattr(logging, self.device.get('logLevel', 'WARN'))
    address = self.device.get('logAddress', '/dev/log')
    log.setLevel(level)
    for previous in log.handlers[:]:
      log.removeHandler(previous)
    log.addHandler(logging.handlers.SysLogHandler(address=address))
    self.uart = stick.Stick(link.Link(self.scanner( )))
    self.uart.open( )
    serial = self.device.get('serial')
    self.pump = session.Pump(self.uart, serial)
    stats = self.uart.interface_stats( )
  def main (self, args, app):
    return self.scanner( )

@use( )
class config (MedtronicTask):
  requires_session = False

  def before_main (self, args, app):
    # self.setup_medtronic( )
    self.session = self.read_session_file( )

  def configure_app (self, app, parser):
    parser.add_argument('-M', '--model', default=None)
    parser.add_argument('-S', '--serial', default='')
    parser.add_argument('-R', '--reset-expires', action='store_true', default=False)
    # parser.add_argument('-5', '--G5', dest='model', const='G5', action='store_const', default=None)
  def main (self, args, app):
    results = dict(**self.device.extra.fields)
    results.update(self.session)
    dirty = False
    if args.model:
      results.update(model=args.model)
      self.session.update(model=args.model)
      self.device.extra.add_option('model', args.model.upper( ))
      dirty = True
    if args.serial:
      results.update(serial=args.serial)
      self.device.extra.add_option('serial', args.serial.upper( ))
      dirty = True
    self.save_session = False
    if args.reset_expires:
      print "resetting {0} session".format(self.device.name)
      self.session.update(model='', expires=datetime.now( ))
      self.save_session = True


    self.uart = None
    if dirty:
      # self.session.update(expires=self.session.get('expires', datetime.now( )))
      self.device.store(app.config)
      app.config.save( )
    return results

class Session (MedtronicTask):
  """ session for pump
  """
  requires_session = False
  def configure_parser (self, parser):
    parser.add_argument('--minutes', type=int, default='10')
  def setup_application (self):
    """
    """
  def main (self, args, app):
    info = self.create_session( )
    info.update(**self.update_session_info(info))
    return info

@use( )
class model (MedtronicTask):
  """ Get model number [#oref0] [#recommended] [#safe]

  This is one of the safest commands available.
  """
  def configure_app (self, app, parser):
    pass
  def main (self, args, app):
    model = self.pump.read_model( ).getData( )
    return model

@use( )
class read_status (MedtronicTask):
  """ Get pump status
  """
  def main (self, args, app):
    return self.pump.model.read_status( )

@use( )
class status (read_status):
  """ Get pump status (alias for read_status)
  """

@use( )
class reservoir (MedtronicTask):
  """ Get pump remaining insulin
  """
  def main (self, args, app):
    return self.pump.model.read_reservoir( )

@use( )
class settings (MedtronicTask):
  """ Get pump settings
  """
  def main (self, args, app):
    return self.pump.model.read_settings( )

@use( )
class mytest (MedtronicTask):
  """ Testing read_settings
  """
  requires_session = False
  def main (self, args, app):
    return self.pump.model.my_read_settings( )

class key_presser (MedtronicTask):
  def run_presses (self, recipe):
    results = [ ]
    for press in recipe:

      pressed = self.pump.model.press_key(press)
      results.append(pressed)
    successes = filter(lambda x: x['received'], results)
    completed = len(successes) == len(recipe)
    response = dict(results=results, completed=completed)

    return response

@use( )
class press_keys (key_presser):
  """ Press keys
  """

  def from_ini (self, fields):
    fields['input'] = fields.get('input', '').upper( ).split(' ')
    return fields
  def to_ini (self, args):
    params = self.get_params(args)
    params['input'] = ' '.join(params.get('input', [])).upper( )
    return params
  def configure_app (self, app, parser):
    keys = 'ESC ACT UP DOWN EASY'.split(' ')
    keys.extend([k.lower( ) for k in keys[:]])
    parser.add_argument('input', nargs=argparse.REMAINDER,  choices=keys)
    return parser

  def get_params (self, args):
    # return dict(input=args.input)
    return dict(input=[k.upper( ) for k in args.input])


  def main (self, args, app):
    params = self.get_params(args)
    recipe = params.get('input', [ ])

    results = self.run_presses(recipe)

    return results

@use( )
class test_oref0_compat_menu (key_presser):
  recipe = [ 'DOWN', 'ESC' ] + ([ 'DOWN' ] * 13 )
  def main (self, args, app):

    results = self.run_presses(self.recipe)

    return results



@use( )
class read_clock (MedtronicTask):
  """ Read date/time of pump [#oref0]
  """
  def main (self, args, app):
    return self.pump.model.read_clock( )


class SameNameCommand (MedtronicTask):
  def main (self, args, app):
    name = self.__class__.__name__.split('.').pop( )
    return getattr(self.pump.model, name)(**self.get_params(args))

class SelectedNameCommand (MedtronicTask):
  def main (self, args, app):
    name = self.selected
    return getattr(self.pump.model, name)(**self.get_params(args))


@use( )
class read_temp_basal (SameNameCommand):
  """ Read temporary basal rates. [#oref0] """

@use( )
class read_settings (SameNameCommand):
  """ Read settings. [#oref0] """

@use( )
class read_carb_ratios (SameNameCommand):
  """ Read carb_ratios. [#oref0] """

@use( )
class read_basal_profile_std (SameNameCommand):
  """ Read default basal profile. """

@use( )
class read_basal_profile_A (SameNameCommand):
  """ Read basal profile A. """

@use( )
class read_basal_profile_B (SameNameCommand):
  """ Read basal profile B. """

@use( )
class read_selected_basal_profile (SameNameCommand):
  """ Fetch the currently selected basal profile. [#oref0] """

@use( )
class read_current_glucose_pages (SameNameCommand):
  """ Read current glucose pages. """

@use( )
class read_current_history_pages (SameNameCommand):
  """ Read current history pages. """

@use( )
class suspend_pump (SameNameCommand):
  """ Suspend pumping. """
  def main (self, args, app):
    result = super(suspend_pump, self).main(args, app)
    result.update(enacted_at=datetime.now( ))
    return result

@use( )
class resume_pump (suspend_pump):
  """ resume pumping. """

@use( )
class read_battery_status (SameNameCommand):
  """ Check battery status. [#oref0] """

@use( )
class read_bg_targets (SelectedNameCommand):
  """ Read bg targets. [#oref0] """
  selected = 'read_bg_targets'

@use( )
class read_insulin_sensitivies (SameNameCommand):
  """ XXX: Deprecated.  Don't use.  Use read_insulin_sensitivities instead. """


@use( )
class read_insulin_sensitivities (SameNameCommand):
  """ Read insulin sensitivities. [#oref0] """


@use( )
class read_glucose_data (SameNameCommand):
  """ Read pump glucose page
  """
  def configure_app (self, app, parser):
    parser.add_argument('page', type=int, default=0)

  def get_params (self, args):
    return dict(page=int(args.page))

class InputProgramRequired (MedtronicTask):
  def upload_program (self, program):
    raise NotImplementedError( )
  def get_params (self, args):
    return dict(input=args.input)
  def configure_app (self, app, parser):
    parser.add_argument('input', default='-')
  def get_program (self, args):
    params = self.get_params(args)
    program = json.load(argparse.FileType('r')(params.get('input')))
    return program
  def main (self, args, app):
    program = self.get_program(args)
    results = self.upload_program(program)
    program.update(timestamp=datetime.now( ), **results)
    return program

def parse_clock (candidate):
  if candidate.lower( ) in ['now']:
    return datetime.now( )
  return parse(candidate)
@use( )
class set_clock (InputProgramRequired):
  """ Set clock.


  -------------------


  input should be the name of a json file, or `-` for stdin.
  The json file should contain a key named `clock` with the new
  requested value formatted as ISO 8601 including seconds.


      { "clock": "2016-03-14T14:23:40" }


  -------------------


  `--to` switch
  -------------------


  Alternatively, the `--to` switch maybe used:
  The keyword `now` may be given to automatically generate a request
  using the system's current time.  Otherwise, the value must be
  something that can be parsed as an ISO 8601 formatted time including
  the seconds.


      --to now
      --to $(date -Iseconds)
      --to 2016-03-14T14:29:41-0700

  """
  def get_params (self, args):
    return dict(input=args.input, to=args.to)
  def configure_app (self, app, parser):
    parser.add_argument('input', nargs='?', default=None)
    # parser.add_argument('input', nargs='?', default='-')
    parser.add_argument('--to', default=None)
  def upload_program (self, program):
    if not program.get('clock', None):
      print "Bad input"
      raise Exception("Bad input, missing clock definition: {0}".format(program.get('clock')))
    return self.pump.model.set_clock(**program)
    # return dict(test_ok=dict(**program))
  def get_program (self, args):
    params = self.get_params(args)
    program = dict(clock=None)
    if params.get('to', None) is None and params.get('input'):
      program.update(clock=parse(json.load(argparse.FileType('r')(params.get('input')))))
    else:
      if params.get('to'):
        program.update(clock=parse_clock(params.get('to')))
    return program
@use( )
class set_temp_basal (InputProgramRequired):
  """ Set temporary basal rates. [#oref0]

  Requires json input with the following keys defined:
    * `temp` - the type of temporary rate, `percent` or `absolute`
    * `rate` - The temporary rate, in units.  Examples, 0.0, 1.2, 0.1
    * `duration` - The duration in minutes of the temporary rate.  The duration must be multiples of 30 minutes.


  Eg, actively canceling a rate:
  { "temp": "absolute", "rate": 0, "duration": 0 }


  Zero basal for half hour:
  { "temp": "absolute", "rate": 0, "duration": 30 }


  One and a half units for one hour:
  { "temp": "absolute", "rate": 1.5, "duration": 60 }
  """
  required_inputs = [ 'duration', 'rate' ]
  def upload_program (self, program):
    missing = [ ]
    for req in self.required_inputs:
      if not req in program:
        missing.append(req)
    if len(missing) > 0:
      return dict(error="missing required input fields", missing=missing, input=dict(**program))
    return self.pump.model.set_temp_basal(**program)

@use( )
class bolus (InputProgramRequired):
  """Send bolus command. [#warning!!!]

  Beware! This is a powerful command because it can give a lot of
  insulin.  Please be careful!
  Not a part of oref0.


  -----------------------


  Requires json input with the following keys defined:
    * `units` - Number of units to bolus.


  Zero point one units:
  { "units": 0.1 }


  Two units:
  { "units": 2 }
  """
  def upload_program (self, program):
    return self.pump.model.bolus(**program)

@use( )
class filter_glucose_date (SameNameCommand):
  """ Search for glucose pages including begin and end dates (iso 8601).
  """
  def get_params (self, args):
    return dict(begin=args.begin, end=args.end)
  def configure_app (self, app, parser):
    parser.add_argument('begin', default='')
    parser.add_argument('end', default='')

@use( )
class filter_isig_date (filter_glucose_date):
  """ Search for isig pages including begin and end dates (iso 8601).
  """

@use( )
class read_history_data (MedtronicTask):
  """ Read pump history page
  """
  def get_params (self, args):
    return dict(page=int(args.page))
  def configure_app (self, app, parser):
    parser.add_argument('page', type=int, default=0)

  def main (self, args, app):
    history = self.pump.model.read_history_data(**self.get_params(args))
    return history


@use( )
class iter_glucose (MedtronicTask):
  """ Read latest 100 glucose records
  """
  def get_params (self, args):
    return dict(count=int(args.count))
  def configure_app (self, app, parser):
    parser.add_argument('count', type=int, default=99)
  def range (self):
    return self.pump.model.iter_glucose_pages( )
  maxCount = 99
  def main (self, args, app):
    self.maxCount = self.get_params(args).get('count', self.maxCount)
    num = 0
    records = [ ]
    for rec in self.range( ):
      records.append(rec)
      num = num + 1
      if num > self.maxCount:
        break
    return records

@use( )
class iter_pump (iter_glucose):
  """ Read latest 100 pump records
  """
  def range (self):
    return self.pump.model.iter_history_pages( )


@use ( )
class iter_glucose_hours (MedtronicTask):
  """ Read latest n hours of glucose data
  """
  def get_params (self, args):
    params = dict(hours=float(args.hours))

    if 'now' in args and args.now is not None:
      params.update(now=args.now)

    return params

  def configure_app (self, app, parser):
    parser.add_argument('hours', type=float, help='The number of hours of historical data to retrieve')
    parser.add_argument('--now', help='A read_clock report filename from which to offset the hours')

  def range (self):
    return self.pump.model.iter_glucose_pages( )

  def get_record_timestamp (self, record):
    return parse(record['date']) if 'date' in record else None

  def main (self, args, app):
    params = self.get_params(args)
    min_offset = relativedelta.relativedelta(hours=params['hours'])
    min_timestamp = parse(json.load(argparse.FileType('r')(params['now']))) - min_offset if 'now' in params else None

    records = [ ]
    for rec in self.range( ):
      timestamp = self.get_record_timestamp(rec)

      if timestamp is not None and min_timestamp is None:
        min_timestamp = timestamp - min_offset

      if timestamp is None or timestamp >= min_timestamp:
        records.append(rec)
      else:
        break
    return records


@use ( )
class iter_pump_hours (iter_glucose_hours):
  """ Read latest n hours of pump records
  """
  def range (self):
    return self.pump.model.iter_history_pages( )

  def get_record_timestamp (self, record):
    return parse(record['timestamp']) if 'timestamp' in record else None


def set_config (args, device):
  device.add_option('serial', args.serial)

def display_device (device):
  return ''

known_uses = [
  Session,
]
def get_uses (device, config):
  all_uses = known_uses[:] + use.get_uses(device, config)
  all_uses.sort(key=lambda usage: getattr(usage, 'sortOrder', usage.__name__))
  return all_uses
