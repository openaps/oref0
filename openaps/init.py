
import os

def init (args):
  shell_cmd = ['git-openaps-init' ] + args.args
  os.execvp(shell_cmd[0], shell_cmd)

