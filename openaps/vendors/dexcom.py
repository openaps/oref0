
"""
Dexcom - openaps driver for dexcom
"""
from openaps.uses.use import Use
from openaps.uses.registry import Registry
import dexcom_reader
from dexcom_reader import readdata
from dexcom_reader import database_records
from datetime import timedelta
from datetime import datetime
import dateutil
from dateutil import relativedelta
from dateutil.parser import parse
import json
import itertools
import time
import argparse
import socket

def set_config (args, device):
  return

def display_device (device):
  return ''

use = Registry( )

get_uses = use.get_uses


@use( )
class scan (Use):
  """ scan for usb stick """
  def scanner (self):
    return self.device.get('usbPort', readdata.Dexcom.FindDevice( ))
    return readdata.Dexcom.FindDevice( )
  def before_main (self, args, app):
    self.port = self.scanner( )
    # set model = G5 in config
    model = self.device.get('model', 'G4').upper( )
    G5 = model == 'G5'
    self.dexcom = self.port and readdata.GetDevice(self.port, G5=G5) or None
  def main (self, args, app):
    return self.port or ''

@use( )
class config (Use):
  def configure_app (self, app, parser):
    parser.add_argument('-M', '--model', default=None)
    parser.add_argument('-5', '--G5', dest='model', const='G5', action='store_const', default=None)
  def main (self, args, app):
    results = dict(**self.device.extra.fields)
    dirty = False
    if args.model:
      results.update(model=args.model)
      self.device.extra.add_option('model', args.model.upper( ))
      dirty = True

    if dirty:
      self.device.store(app.config)
      app.config.save( )
    return results
@use( )
class battery (scan):
  def main (self, args, app):
    battery = dict( level=self.dexcom.ReadBatteryLevel( )
                  , status=self.dexcom.ReadBatteryState( )
                  )
    return battery

@use( )
class ReadBatteryLevel (scan):
  def main (self, args, app):
    return self.dexcom.ReadBatteryLevel( )

@use( )
class ReadBatteryState (scan):
  def main (self, args, app):
    return self.dexcom.ReadBatteryState( )

@use( )
class ReadManufacturingData (scan):
  def main (self, args, app):
    data = self.dexcom.ReadManufacturingData( )
    result = data.attrib
    return result

@use( )
class GetFirmwareHeader (scan):
  def main (self, args, app):
    data = self.dexcom.GetFirmwareHeader( )
    result = data.attrib
    return result

def parse_clock (candidate):
  if candidate.lower( ) in ['now']:
    return datetime.now( )
  return parse(candidate)

@use( )
class UpdateTime (scan):
  """Update receiver time """
  def get_params (self, args):
    return dict(input=args.input, to=args.to)
  def configure_app (self, app, parser):
    parser.add_argument('input', nargs='?', default=None)
    parser.add_argument('--to', default=None)
  def upload_program (self, program):
    if not program.get('clock', None) or 'offset' not in program:
      print "Bad input"
      raise Exception("Bad input, missing clock definition: {0}".format(program.get('clock')))
    result = self.dexcom.WriteDisplayTimeOffset(offset=program['offset'])
    new_offset = self.dexcom.ReadDisplayTimeOffset( )
    return dict(requested=dict(**program), result=result, offset=new_offset.total_seconds( ))
  def get_program (self, args):
    params = self.get_params(args)
    program = dict(clock=None)
    if params.get('to', None) is None and params.get('input'):
      program.update(clock=parse(json.load(argparse.FileType('r')(params.get('input')))))
    else:
      if params.get('to'):
        program.update(clock=parse_clock(params.get('to')))
    current_utc = self.dexcom.ReadSystemTime( )
    offset = program['clock'] - current_utc
    program.update(offset=offset.total_seconds( ))

    return program
  def main (self, args, app):
    program = self.get_program(args)
    results = self.upload_program(program)
    program.update(enacted_at=datetime.now( ), **results)
    return program

@use( )
class WriteChargerCurrentSetting (scan):
  MAP = [ 'Off', 'Power100mA', 'Power500mA', 'PowerMax', 'PowerSuspended' ]
  def get_params (self, args):
    return dict(status=args.status)
  def configure_app (self, app, parser):

    parser.add_argument('--status', dest='status', choices=self.MAP)
    for key in self.MAP:
      flag = "--{0}".format(key)
      parser.add_argument(flag, dest='status', action='store_const', const=key)

  def main (self, args, app):
    params = self.get_params(args)
    status = params.get('status')
    requested = dict(**params)
    if not status:
      raise Exception("requested ChargeCurrent setting unknown: {0}".format(status))
    result = self.dexcom.WriteChargerCurrentSetting(status)
    updated = self.dexcom.ReadChargerCurrentSetting( )
    result.update(enacted_at=datetime.now( ), status=updated, requested=requested)
    return result

@use( )
class DescribeClocks (scan):
  """Describe all the clocks """
  def main (self, args, app):
    system = dict(offset=self.dexcom.ReadSystemTimeOffset( ).total_seconds( )
                 , utc=self.dexcom.ReadSystemTime( ))
    # system.update
    display = dict(offset=self.dexcom.ReadDisplayTimeOffset( ).total_seconds( )
                  , clock=self.dexcom.ReadDisplayTime( ))
    rtc = dict(epoch=self.dexcom.ReadRTC( ))
    clocks = dict(system=system, display=display, rtc=rtc)
    return clocks

@use( )
class ReadTransmitterId (scan):
  def main (self, args, app):
    result = self.dexcom.ReadTransmitterId( )
    return result

class SameNameCommand (scan):
  def pass_result (self, result):
    return result
  def main (self, args, app):
    name = self.__class__.__name__.split('.').pop( )
    result = getattr(self.dexcom, name)(**self.get_params(args))
    return self.pass_result(result)

@use( )
class ReadLanguage (SameNameCommand):
  """Read Language """


@use( )
class ReadRTC (SameNameCommand):
  """Read RTC """

@use( )
class ReadSystemTime (SameNameCommand):
  """Read System Time """

@use( )
class ReadSystemTimeOffset (SameNameCommand):
  """Read System Time Offset"""
  def pass_result (self, result):
    return result.total_seconds( )

@use( )
class ReadDisplayTime (SameNameCommand):
  """Read Display Time Offset"""

@use( )
class ReadDisplayTimeOffset (ReadSystemTimeOffset):
  """Read Display Time Offset"""

@use( )
class ReadGlucoseUnit (SameNameCommand):
  """Read Glucose Unit """

@use( )
class ReadClockMode (SameNameCommand):
  """Read Clock Mode """


@use( )
class ReadDeviceMode (SameNameCommand):
  """Read Device Mode """

@use( )
class ReadBlindedMode (SameNameCommand):
  """Read Blinded Mode """

@use( )
class ReadHardwareBoardId (SameNameCommand):
  """Read Hardware board ID  """

@use( )
class ReadSetupWizardState (SameNameCommand):
  """Read Setup wizard state """

@use( )
class ReadChargerCurrentSetting (SameNameCommand):
  """Read Charger current setting """






@use( )
class glucose (scan):
  """ glucose

  This is a good example of what is needed for new commands.
  To add additional commands, subclass from scan as shown.
  """
  RECORD_TYPE = 'EGV_DATA'
  TEXT_COLUMNS = [ 'display_time', 'glucose', 'trend_arrow' ]
  def prerender_stdout (self, data):
    return self.prerender_text(data)
  def prerender_text (self, data):
    """ turn everything into a string """
    out = [ ]
    for item in data:
      line = map(str, [ item[field] for field in self.TEXT_COLUMNS ])
      out.append(' '.join(line))
    return "\n".join(out)
  def prerender_json (self, data):
    """ since everything is a dict/strings/ints, we can pass thru to json """
    return data
  def main (self, args, app):
    """
    Implement a main method that takes args and app as parameters.
    Use self.dexcom.Read... to get data.
    Return the resulting data for this task/command.
    The data will be passed to prerender_<format> by the reporting system.
    """
    # records = self.dexcom.ReadRecords('EGV_DATA')
    records = self.dexcom.ReadRecords(self.RECORD_TYPE)
    # return list of dicts, easier for json
    out = [ ]
    for item in records:
      # turn everything into dict
      out.append(item.to_dict( ))
    return out

def none_to_ini (field):
  if field in [ '', 'None', None ]:
    field = ''
  return field

def none_from_ini (field):
  if field in [ '', 'None', None ]:
    field = None
  return field


class GapFiller (object):
  @classmethod
  def add_argument (cls, parser):
    parser.add_argument('-G', '--gaps', help='')
    parser.add_argument('-n', '--count', type=int, default=None, help='')
    parser.add_argument('-D', '--date', action="append", default=["display_time"], help='Date field selector')
    parser.add_argument('--hours', type=float, nargs='?', default=None,
                        help="Number of hours of glucose records to read.")
    parser.add_argument('--minutes', type=float, nargs='?', default=None,
                        help="Number of minutes of glucose records to read.")
    parser.add_argument('--seconds', type=float, nargs='?', default=None,
                        help="Number of seconds of glucose records to read.")
    parser.add_argument('--microseconds', type=int, nargs='?', default=None,
                        help="Number of milliseconds seconds of glucose records to read.")
    # parser.add_argument('--since', default='now', help='Get all records since this date with the delta applied.')
  @classmethod
  def to_ini (cls, params, args):
    gaps = params.get('gaps', '')
    if gaps in [ '', 'None', None ]:
      gaps = ''

    for field in ['count', 'microseconds', 'seconds', 'minutes', 'hours']:
      params[field] = none_to_ini(params.get(field))
    params.update(gaps=gaps, date=' '.join(params.get('date', [ ])))
    return params
  @classmethod
  def from_ini (cls, fields):
    gaps = fields.get('gaps', '')
    if gaps in [ '', 'None' ]:
      gaps = None
    fields.update(gaps=gaps, date=fields.get('date', 'display_time').split(' '))
    for field in ['count', 'microseconds', 'seconds', 'minutes', 'hours']:
      fields[field] = none_from_ini(fields.get(field))
      if field in [ 'microseconds', 'count', ]:
        if fields[field]:
          fields[field] = int(fields[field])
      if field in [ 'seconds', 'hours', 'minutes', ]:
        if fields[field]:
          fields[field] = float(fields[field])
    return fields
  def __init__ (self, app):
    self.method = app
    # print app, app.__dict__

  def itertool (self, app, count=None, **params):
    self.count = count
    self.since = None
    self.records = [ ]
    rel = dict(hours=params.get('hours', 0), minutes=params.get('minutes', 0), seconds=params.get('seconds', 0), microseconds=params.get('microseconds', 0))
    for x in rel.keys( ):
      if rel[x] is None:
        rel.pop(x)

    if len(rel) > 0:
      delta = relativedelta.relativedelta(**rel)
      now = datetime.now( )
      if params.get('gaps'):
        now = self.get_gaps(params.get('gaps'))
      self.since = now - delta
    return self
  def get_gaps (self, gaps):
    oldest = None
    if gaps:
      gaps = json.load(argparse.FileType('r')(gaps))
      oldest = parse(gaps[0].get('prev'))
      for gap in gaps:
        current = parse(gap.get('prev'))
        if current < oldest:
          oldest = current
    return oldest.replace(tzinfo=None)


  def __call__ (self, item):
    return not self.excludes(item) and self.includes(item)
  def includes (self, elem):
    if self.since:
      return self.getDate(elem) >= self.since
    else:
      return True
  def excludes (self, item):
    if self.count:
      if len(self.records) >= self.count:
        return True
    return False


  def getDate (self, item):
    return self.method.get_item_date(item)

@use( )
class iter_glucose (glucose):
  """ read last <count> glucose records, default 100, eg:

* iter_glucose   - read last 100 records
* iter_glucose 2 - read last 2 records
  """
  RECORD_TYPE = 'EGV_DATA'
  def get_params (self, args):
    params = dict(**vars(args))
    if 'action' in params:
      params.pop('action')
    return params
  def configure_app (self, app, parser):
    parser.add_argument('count', type=int, nargs='?', default=100,
                        help="Number of glucose records to read.")
    GapFiller.add_argument(parser)
    self.fill = GapFiller(self)

  def to_ini (self, args):
    params = self.get_params(args)
    params = self.fill.to_ini(params, args)
    return params
  def from_ini (self, fields):
    fields = self.fill.from_ini(fields)
    return fields

  def get_item_date (self, elem):
    return getattr(elem, self.dateSelector)

  def main (self, args, app):
    # records = [ ]
    params = self.get_params(args)
    self.dateSelector = params.get('date')[0]
    self.comparison = self.fill.itertool(app, **params)
    candidates = itertools.takewhile(self.comparison, self.dexcom.iter_records(self.RECORD_TYPE))
    records = self.fill.records
    for item in candidates:
      records.append(item.to_dict( ))
      # print len(records)
      if len(records) >= self.get_params(args)['count']:
        break
    return records


import collections
_EGVRecord = collections.namedtuple('EGV', database_records.EGVRecord.BASE_FIELDS + database_records.EGVRecord.FIELDS + [ 'full_trend'])
class EGVRecord (_EGVRecord):
  def to_dict (self):
    kwds = self._asdict( )
    kwds['display_time'] = self.display_time.isoformat( )
    return kwds
_SensorRecord = collections.namedtuple('Sensor', database_records.SensorRecord.BASE_FIELDS + database_records.SensorRecord.FIELDS)
class SensorRecord (_SensorRecord):
  def to_dict (self):
    kwds = self._asdict( )
    kwds['display_time'] = self.display_time.isoformat( )
    return kwds
def fix_display_time (display_time=None, **kwds):
  if display_time:
    kwds['display_time'] = parse(display_time)
  return kwds

def adjust_nightscout_dates (item):
  dt = parse(item['display_time'])
  # http://stackoverflow.com/questions/5022447/converting-date-from-python-to-javascript
  date = (time.mktime(dt.timetuple( ))* 1000 ) + (dt.microsecond / 1000.0)
  item.update(dateString=item['display_time'], date=date)
  return item


@use( )
class oref0_glucose (glucose):
  """ Get Dexcom glucose formatted for Nightscout, merged with raw data.  [#oref0]

  """

  TEXT_COLUMNS = glucose.TEXT_COLUMNS + [  ]
  def get_params (self, args):
    # params = dict(hours=float(args.hours), threshold=args.threshold)
    params = dict(**vars(args))
    if 'action' in params:
      params.pop('action')
    return params
  def to_ini (self, args):
    params = self.get_params(args)

    params['glucose'] = none_to_ini(args.glucose)
    params['sensor'] = none_to_ini(args.sensor)
    if args.no_raw:
      params['no_raw'] = True
    params = self.fill.to_ini(params, args)
    return params
  def from_ini (self, fields):
    fields['glucose'] = none_from_ini(fields.get('glucose', None))
    fields['sensor'] = none_from_ini(fields.get('sensor', None))
    fields['no_raw'] = 'no_raw' in fields and fields.get('no_raw', 'True') == 'True'
    fields = self.fill.from_ini(fields)
    return fields

  def configure_app (self, app, parser):
    parser.add_argument('--threshold', type=int,  default=100,
                        help="Merge EGV and Sensor records occuring within THRESHOLD seconds of each other.")
    parser.add_argument('--no-raw',  action='store_true', default=False,
                        help="Skip raw data.")
    parser.add_argument('--glucose', default=None,
                        help="File to read glucose from instead of device.")
    parser.add_argument('--sensor', default=None,
                        help="File to read sensor (raw) from instead of device.")
    GapFiller.add_argument(parser)
    self.fill = GapFiller(self)

  def adjust_dates (self, item):
    return adjust_nightscout_dates(item)
    dt = parse(item['display_time'])
    # http://stackoverflow.com/questions/5022447/converting-date-from-python-to-javascript
    date = (time.mktime(dt.timetuple( ))* 1000 ) + (dt.microsecond / 1000.0)
    item.update(dateString=item['display_time'], date=date)
    return item

  def get_glucose_data (self, params, args):
    if args.glucose:
      # return [EGVRecord(**item) for item in json.load(argparse.FileType('r')(args.glucose))]
      results = [ ]
      for item in json.load(argparse.FileType('r')(args.glucose)):
        if not 'full_trend' in item:
          item['full_trend'] = self.arrow_to_trend(item['trend_arrow'])
        record = EGVRecord(**fix_display_time(**item))
        results.append(record)
      return results
    return itertools.takewhile(self.comparison, self.dexcom.iter_records('EGV_DATA'))
  def get_sensor_data (self, params, args):
    if args.no_raw:
      return [ ]
    else:
      if args.sensor:
        return [SensorRecord(**fix_display_time(**item)) for item in json.load(argparse.FileType('r')(args.sensor))]
      else:
        return itertools.takewhile(self.comparison, self.dexcom.iter_records('SENSOR_DATA'))

  def get_item_date (self, elem):
    return getattr(elem, self.dateSelector)
  def main (self, args, app):
    params = self.get_params(args)
    self.dateSelector = params.get('date')[0]

    self.comparison = self.fill.itertool(app, **params)
    records = self.fill.records

    iter_glucose = self.get_glucose_data(params, args)
    iter_sensor  = self.get_sensor_data(params, args)
    template = dict(device="openaps://{}/{}".format(socket.gethostname(),self.device.name), type='sgv')
    for egv, raw in itertools.izip_longest(iter_glucose, iter_sensor):
      item = dict(**template)
      if egv:
        # trend = getattr(egv, 'full_trend', self.arrow_to_trend(egv.trend_arrow))
        trend = self.arrow_to_trend(egv.trend_arrow)
        item.update(sgv=egv.glucose, direction=self.trend_to_direction(trend, egv.trend_arrow), **egv.to_dict( ))
        # https://github.com/nightscout/cgm-remote-monitor/blob/dev/lib/mqtt.js#L233-L296
        if raw:
          delta = abs((raw.display_time - egv.display_time).total_seconds( ))
          if delta < args.threshold:
            item.update(filtered=raw.filtered, unfiltered=raw.unfiltered, rssi=raw.rssi)
          else:
            # create two items instead of one
            # if raw:
            self.adjust_dates(item)
            records.append(item)
            item = dict(sgv=-1, **template)
            item.update(**raw.to_dict( ))

        self.adjust_dates(item)
        records.append(item)
          # item = dict( )
      elif raw:
        item.update(type='sgv', sgv=-1, **raw.to_dict( ))
        self.adjust_dates(item)
        records.append(item)

    return records

  @staticmethod
  def arrow_to_trend (arrow):
    VALUES = dexcom_reader.constants.TREND_ARROW_VALUES
    if arrow in VALUES:
      return VALUES.index(arrow)
  @classmethod
  def trend_to_direction (Klass, trend, arrow):
    dexcom_reader.constants.TREND_ARROW_VALUES
    TREND_ARROW_VALUES = [None, 'DOUBLE_UP', 'SINGLE_UP', '45_UP', 'FLAT',
                          '45_DOWN', 'SINGLE_DOWN', 'DOUBLE_DOWN', 'NOT_COMPUTABLE',
                          'OUT_OF_RANGE']
    DIRECTIONS = Klass.NS_DIRECTIONS

    # NAMES = [ name for name, v in DIRECTIONS.items( ) ]
    NAMES = Klass.NS_NAMES
    return NAMES[trend]

  NS_NAMES = [
      None
    , 'DoubleUp'
    , 'SingleUp'
    , 'FortyFiveUp'
    , 'Flat'
    , 'FortyFiveDown'
    , 'SingleDown'
    , 'DoubleDown'
    , 'NOT COMPUTABLE'
    , 'RATE OUT OF RANGE'
    ]
  NS_DIRECTIONS = {
    None: 0
    , 'DoubleUp': 1
    , 'SingleUp': 2
    , 'FortyFiveUp': 3
    , 'Flat': 4
    , 'FortyFiveDown': 5
    , 'SingleDown': 6
    , 'DoubleDown': 7
    , 'NOT COMPUTABLE': 8
    , 'RATE OUT OF RANGE': 9
  }


@use( )
class iter_glucose_hours (glucose):
  """ read last <hours> of glucose records, default 1, eg:

* iter_glucose_hours     - read last 1 hour of glucose records
* iter_glucose_hours 4.3 - read last 4.3 hours of glucose records
  """

  def get_params (self, args):
    return dict(hours=float(args.hours))

  def configure_app (self, app, parser):
    parser.add_argument('hours', type=float, nargs='?', default=1,
                        help="Number of hours of glucose records to read.")

  def main (self, args, app):
    params = self.get_params(args)
    delta = relativedelta.relativedelta(hours=params.get('hours'))
    now = datetime.now( )
    since = now - delta
    records = [ ]
    for item in self.dexcom.iter_records(self.RECORD_TYPE):
      if item.display_time >= since:
        records.append(item.to_dict( ))
      else:
        break
    return records


@use( )
class sensor (glucose):
  """Fetch Sensor (raw) records from Dexcom receiver.

  Fetches raw records.
  """
  RECORD_TYPE = 'SENSOR_DATA'
  TEXT_COLUMNS = [ 'display_time', 'unfiltered', 'filtered', 'rssi' ]

@use( )
class iter_sensor (iter_glucose, sensor):
  RECORD_TYPE = 'SENSOR_DATA'
  TEXT_COLUMNS = [ 'display_time', 'unfiltered', 'filtered', 'rssi' ]

@use( )
class iter_sensor_hours (iter_glucose_hours, iter_sensor):
  RECORD_TYPE = 'SENSOR_DATA'
  TEXT_COLUMNS = [ 'display_time', 'unfiltered', 'filtered', 'rssi' ]


@use( )
class meter_data (sensor):
  """
  Fetch METER_DATA records from the Dexcom receiver.
  """
  RECORD_TYPE = 'METER_DATA'
  TEXT_COLUMNS = [ 'display_time', 'system_time', 'meter_time', 'meter_glucose'  ]

@use( )
class iter_meter_data (iter_sensor, meter_data):
  RECORD_TYPE = 'METER_DATA'
  TEXT_COLUMNS = meter_data.TEXT_COLUMNS

@use( )
class iter_meter_data_hours (iter_sensor_hours, iter_meter_data):
  RECORD_TYPE = 'METER_DATA'
  TEXT_COLUMNS = meter_data.TEXT_COLUMNS


@use( )
class insertion_time (sensor):
  """
  Fetch INSERTION_TIME records from the Dexcom receiver.

  These are created when sensors are started.
  """
  RECORD_TYPE = 'INSERTION_TIME'
  TEXT_COLUMNS = [ 'display_time', 'system_time', 'insertion_time', 'session_state' ]

@use( )
class iter_insertion_time (iter_sensor, insertion_time):
  RECORD_TYPE = insertion_time.RECORD_TYPE
  TEXT_COLUMNS = insertion_time.TEXT_COLUMNS

@use( )
class iter_insertion_time_hours (iter_sensor_hours, iter_insertion_time):
  RECORD_TYPE = insertion_time.RECORD_TYPE
  TEXT_COLUMNS = insertion_time.TEXT_COLUMNS



@use( )
class user_event_data (sensor):
  """
  Fetch USER_EVENT_DATA records from the Dexcom receiver.
  """
  RECORD_TYPE = 'USER_EVENT_DATA'
  TEXT_COLUMNS = [ 'display_time', 'system_time', 'event_type', 'event_sub_type', 'event_value' ]


@use( )
class iter_user_event_data (iter_sensor, user_event_data):
  RECORD_TYPE = user_event_data.RECORD_TYPE
  TEXT_COLUMNS = user_event_data.TEXT_COLUMNS

@use( )
class iter_user_event_data_hours (iter_sensor_hours, iter_user_event_data):
  RECORD_TYPE = user_event_data.RECORD_TYPE
  TEXT_COLUMNS = user_event_data.TEXT_COLUMNS

@use( )
class sensor_insertions (scan):
  """ read sensor insertion, removal, and expiration records of sensors

  """
  def prerender_stdout (self, data):
    return self.prerender_text(data)
  def prerender_text (self, data):
    """ turn everything into a string """
    out = [ ]
    for item in data:
      line = map(str, [
        item['system_time']
      , item['insertion_time']
      , item['session_state']
      , item['display_time']
      ])
      out.append(' '.join(line))
    return "\n".join(out)
  def prerender_json (self, data):
    """ since everything is a dict/strings/ints, we can pass thru to json """
    return data
  def main (self, args, app):
    """
    Implement a main method that takes args and app as parameters.
    Use self.dexcom.Read... to get data.
    Return the resulting data for this task/command.
    The data will be passed to prerender_<format> by the reporting system.
    """
    records = self.dexcom.ReadRecords('INSERTION_TIME')
    # return list of dicts, easier for json
    out = [ ]
    for item in records:
      # turn everything into dict
      out.append(item.to_dict( ))
    return out

@use( )
class iter_sensor_insertions (sensor_insertions):
  """ read last <count> sensor insertion, removal, and expiration records, default 10, eg:

* iter_sensor_insertions   - read last 10 records
* iter_sensor_insertions 2 - read last 2 records
  """
  def get_params (self, args):
    return dict(count=int(args.count))
  def configure_app (self, app, parser):
    parser.add_argument('count', type=int, nargs='?', default=10,
                        help="Number of sensor insertion, removal, and expiration records to read.")

  def main (self, args, app):
    records = [ ]
    for item in self.dexcom.iter_records('INSERTION_TIME'):
      records.append(item.to_dict( ))
      # print len(records)
      if len(records) >= self.get_params(args)['count']:
        break
    return records

@use( )
class iter_sensor_insertions_hours (sensor_insertions):
  """ read last <hours> of sensor insertion, removal, and expiration records, default 1, eg:

* iter_sensor_insertions_hours     - read last 1 hour of sensor insertion, removal, and expiration records
* iter_sensor_insertions_hours 4.3 - read last 4.3 hours of sensor insertion, removal, and expiration records
  """

  def get_params (self, args):
    return dict(hours=float(args.hours))

  def configure_app (self, app, parser):
    parser.add_argument('hours', type=float, nargs='?', default=1,
                        help="Number of hours of sensor insertion, removal, and expiration records to read.")

  def main (self, args, app):
    params = self.get_params(args)
    delta = relativedelta.relativedelta(hours=params.get('hours'))
    now = datetime.now( )
    since = now - delta

    records = [ ]
    for item in self.dexcom.iter_records('INSERTION_TIME'):
      if item.system_time >= since:
        records.append(item.to_dict( ))
      else:
        break
    return records

@use( )
class calibrations (glucose):
  """ read calibration entry records

  """
  RECORD_TYPE = 'CAL_SET'
  TEXT_COLUMNS = database_records.Calibration.BASE_FIELDS + database_records.Calibration.FIELDS




@use( )
class iter_calibrations (calibrations, iter_glucose):
  """ read last <count> calibration records, default 10, eg:

* iter_calibrations   - read last 10 calibration records
* iter_calibrations 2 - read last 2 calibration records
  """
  RECORD_TYPE = 'CAL_SET'

@use( )
class nightscout_calibrations (iter_calibrations):
  """ read calibration records, reformatted for Nightscout and oref0.

  """
  def main (self, args, app):
    results = super(iter_calibrations, self).main(args, app)
    template = dict(device="openaps://{}".format(self.device.name), type='cal')
    for datum in results:
      datum = adjust_nightscout_dates(datum)
      datum.update(dateString=datum.get('display_time'), **template)
    return results

@use( )
class iter_calibrations_hours (calibrations):
  """ read last <hours> of calibration records, default 1, eg:

* iter_calibrations_hours     - read last 1 hour of calibration records
* iter_calibrations_hours 4.3 - read last 4.3 hours of calibration records
  """

  def get_params (self, args):
    return dict(hours=float(args.hours))

  def configure_app (self, app, parser):
    parser.add_argument('hours', type=float, nargs='?', default=1,
                        help="Number of hours of sensor insertion, removal, and expiration records to read.")

  def main (self, args, app):
    params = self.get_params(args)
    delta = relativedelta.relativedelta(hours=params.get('hours'))
    now = datetime.now( )
    since = now - delta

    records = [ ]
    for item in self.dexcom.iter_records('CAL_SET'):
      if item.system_time >= since:
        records.append(item.to_dict( ))
      else:
        break
    return records
