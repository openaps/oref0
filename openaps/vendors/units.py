
"""
Units - units tool for openaps
"""

from openaps.uses.use import Use
from openaps.uses.registry import Registry

from openaps.glucose.convert import Convert as GlucoseConvert

import json
import argparse

def set_config (args, device):
  return device

def display_device (device):
  return ''


use = Registry( )

class ConvertInput (Use):
  def get_params (self, args):
    return dict(input=args.input, to=args.to)
  def configure_app (self, app, parser):
    parser.add_argument('--to','-t', default='mg/dL', choices=['mmol/L', 'mg/dL'])
    parser.add_argument('input', default='-')
  def get_program (self, args):
    params = self.get_params(args)
    program = json.load(argparse.FileType('r')(params.get('input')))
    return program
  CONVERTERS = { 'mmol/L': GlucoseConvert.mg_dl_to_mmol_l
               , 'mg/dL': GlucoseConvert.mmol_l_to_mg_dl }
  def set_converter (self, args):
    params = self.get_params(args)
    converters = self.CONVERTERS
    self.units = params.get('to')
    self.to_unit = converters.get(self.units)

  def convert (self, program):
    raise NotImplementedError( )
  def main (self, args, app):
    self.set_converter(args)
    program = self.get_program(args)
    results = self.convert(program)
    return results

@use( )
class bg_targets (ConvertInput):
  """
    Convert bg_targets json to preferred unit.
  """
  def convert (self, bg_targets):
    assert bg_targets['units'] in ['mg/dL', 'mmol/L']

    if bg_targets['units'] != self.units:
      for target in bg_targets['targets']:
        target['high'] = self.to_unit(target['high'])
        target['low'] = self.to_unit(target['low'])

    bg_targets['user_preferred_units'] = bg_targets['units']
    bg_targets['units'] = self.units

    return bg_targets

@use( )
class insulin_sensitivities (ConvertInput):
  """
    Convert read_insulin_sensitivities json to preferred unit.
  """
  def convert (self, insulin_sensitivities):
    assert insulin_sensitivities['units'] in ['mg/dL', 'mmol/L']
    
    if insulin_sensitivities ['units'] != self.units:
    	for sens in insulin_sensitivities['sensitivities']:
    		sens['sensitivity'] = self.to_unit(sens['sensitivity'])
    	
    insulin_sensitivities['user_preferred_units'] = insulin_sensitivities['units']
    insulin_sensitivities['units'] = self.units
    
    return insulin_sensitivities
    

def get_uses (device, config):
  all_uses = use.get_uses(device, config)
  all_uses.sort(key=lambda usage: getattr(usage, 'sortOrder', usage.__name__))
  return all_uses

