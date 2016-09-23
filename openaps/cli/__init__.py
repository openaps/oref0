
import sys, os
import argparse
import argcomplete
import textwrap

class Base (object):

  always_complete_options = True
  def __init__ (self, args):
    self.inputs = args

  @classmethod
  def _get_description (klass):
    return klass.__doc__.split("\n\n")[0]

  @classmethod
  def _get_epilog (klass):
    return "\n\n".join(klass.__doc__.split("\n\n")[1:])

  def prep_parser (self):
    prog = None
    if self.inputs:
      prog = self.inputs[0]
    epilog = textwrap.dedent(self._get_epilog( ))
    description = self._get_description( )
    self.parser = argparse.ArgumentParser(prog=prog,
                  description=description
                , epilog=epilog
                , formatter_class=argparse.RawDescriptionHelpFormatter)

  def configure_parser (self, parser):
    pass

  def prolog (self):
    pass

  def get_described_parser (self):
    self.prep_parser( )
    self.configure_parser(self.parser)
    return self.parser
  def epilog (self):
    pass

  def __call__ (self):
    self.prep_parser( )
    self.configure_parser(self.parser)
    argcomplete.autocomplete(self.parser, always_complete_options=self.always_complete_options);
    self.args = self.parser.parse_args(self.inputs)
    self.prolog( )
    self.run(self.args)
    self.epilog( )

  def run (self, args):
    print self.inputs
    print args

from openaps import config
class ConfigApp (Base):
  def read_config (self):
    cfg_file = os.environ.get('OPENAPS_CONFIG', 'openaps.ini')
    if not os.path.exists(cfg_file):
      print "Not an openaps environment, run: openaps init"
      sys.exit(1)
    pwd = os.getcwd( )
    cfg_dir = os.path.dirname(cfg_file)
    if cfg_dir and os.getcwd( ) != cfg_dir:
      os.chdir(os.path.dirname(cfg_file))
    self.config = config.Config.Read(cfg_file)

  def prolog (self):
    self.read_config( )

  def epilog (self):
    self.create_git_commit( )
  def git_repo (self):
    from git import Repo, GitCmdObjectDB
    self.repo = getattr(self, 'repo', Repo(os.getcwd( ), odbt=GitCmdObjectDB))
    return self.repo

  def create_git_commit (self):
    self.git_repo( )
    if self.repo.is_dirty( ) or self.repo.index.diff(None):
      # replicate commit -a, automatically add any changed paths
      # should help
      # https://github.com/openaps/openaps/issues/87
      diffs = self.repo.index.diff(None)
      for diff in diffs:
        self.repo.git.add([diff.b_path], write_extension_data=False)
      git = self.repo.git
      msg = """{0:s} {1:s}

      TODO: better change descriptions
      {2:s}
      """.format(self.parser.prog, ' '.join(sys.argv[1:]), ' '.join(sys.argv))
      # https://github.com/gitpython-developers/GitPython/issues/265
      # git.commit('-avm', msg)
      self.repo.index.commit(msg)
    self.repo.git.gc(auto=True)

