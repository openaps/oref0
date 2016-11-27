
import argparse
class Subcommand (object):
  formatter_class = argparse.RawDescriptionHelpFormatter
  def __init__ (self, method=None, parent=None):
    self.method = method
    self.name = method.__name__.split('.').pop( )
    self.parent = parent
    if parent and parent.config:
      self.config = parent.config

  def setup_application (self):
    """ Allows us to use method, injected as dependency earlier to set
    up argparser before autocompletion/running the app.
    """
    # figure out precise method name, specific to this use
    name = 'configure_%s_app' % self.parent.name
    # call generic set up method
    getattr(self.method, 'configure_app', self._no_op_setup)(self, self.parser)
    # call specific set up method
    getattr(self.method, name, self._no_op_setup)(self, self.parser)
  def get_help (self):
    docs = getattr(self.method, '__doc__', "\n\n\n") or "\n\n"
    return ''.join(docs.split("\n\n")[0:1] or "")
  def get_description (self):
    docs = getattr(self.method, '__doc__', "\n\n\n") or "\n\n"
    return ''.join(docs.split("\n\n")[0:1]) or ""

  def get_epilog (self):
    docs = getattr(self.method, '__doc__', "")
    if docs:
      return ''.join(docs.split("\n\n")[1:]) or ""
    return ""

  def configure_subparser (self, subparser):
    parser = subparser.add_parser(self.name,
              help=self.get_help( ),
              description=self.get_description( ),
              epilog=self.get_epilog( ),
              formatter_class=self.formatter_class
              )
    self.parser = parser
    self.setup_application( )
    return parser

  def _no_op_setup (self, parser, app):
    pass
  def _no_op_config (self, parser):
    pass

  def __call__ (self, args, app):
    return self.method.main(args, app)

  def configure_parser (self, parser):
    getattr(self.method, 'configure_parser', self._no_op_config)(parser)

