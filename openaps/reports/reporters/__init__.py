
import base, text, stdout, JSON
import os

def default_prep_stream (reporter):
  name = reporter.report.name
  if not os.path.exists(name):
    directory = os.path.dirname(name)
    if directory and not os.path.exists(directory):
      os.makedirs(directory)
  return open(name, 'w')
def default_close_stream (reporter):
  reporter.output.close( )

class Reporter (object):
  """
  """
  def __init__ (self, report, device, task):
    ""
    self.task   = task
    self.report = report
    self.device = device
    self.method = get_reporter_map( )[report.fields['reporter'].lower( )]
    self.output = getattr(self.method, 'get_output_stream', default_prep_stream)(self)

  def no_op_serialize (self, data):
    return data
  def serialize (self, data):
    name = 'prerender_' + self.report.fields['reporter'].lower( )
    render = getattr(self.task.method, name, self.no_op_serialize)
    return self.method.serialize(render(data), self)
  def __call__ (self, data):
    self.blob = self.serialize(data)
    self.output.write(self.blob)
    self.close( )
  def close (self):
    getattr(self.method, 'close_output_stream', default_close_stream)(self)

def get_reporter_map ( ):
  return dict([ (r.__name__.split('.').pop( ).lower( ), r) for r in get_reporters( ) ])

def get_reporters ( ):
  return [ base, text, stdout, JSON ]

