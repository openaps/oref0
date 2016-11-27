
import init
import alias
import shlex
import cli

from subprocess import call
class BuiltinApp (cli.ConfigApp):
  name = 'builtin'

builtins = {
  'init': init.init
}
def get_builtins ( ):
  app = BuiltinApp([ ])
  app.read_config( )
  out = alias.get_alias_map(app.config)
  out.update(**builtins)
  return out
class RunnableAlias (object):
  def __init__ (self, spec, parent):
    self.spec = spec
    self.parent = parent
  def __call__ (self, args):
    if self.spec is None:
      return None
    spec_command = shlex.split(self.spec.fields.get('command'))
    # print 'YY', spec_command + args.args
    cmd = ['openaps-%s' % spec_command[0]] + spec_command[1:]
    if spec_command[0].startswith('!'):
      prog = shlex.split(spec_command[0][1:])
      cmd = prog + spec_command[1:]
    # print 'XX', cmd + args.args
    exit(call(cmd + args.args))
def get_alias (command, app):
  spec = alias.get_alias_map(app.config).get(command, None)
  runnable = RunnableAlias(spec, app)
  return runnable

def dispatch (args, back):
  app = None
  command = builtins.get(args.command, None)
  if command:
    command(args)
  else:
    app = BuiltinApp(args)
    app.read_config( )
    get_alias(args.command, app)(args)

def is_builtin (command):
  if command in builtins:
    return True
  app = BuiltinApp([ ])
  app.read_config( )
  if command in alias.get_alias_map(app.config):
    return True
  return False

