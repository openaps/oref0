#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)


usage "$@" <<EOF
  Usage:
$self <cmd>

     ______   ______   ______  ______ 0
    / |  | \ | |  | \ | |     | |      
    | |  | | | |__| | | |---- | |----  
    \_|__|_/ |_|  \_\ |_|____ |_|      

Valid commands:
  oref0 device-helper - <name> <spec>  : create/template a device from bash commands easily
  oref0 alias-helper  - <name> <spec>  : create/template a alias from bash commands easily
  oref0 env                            - print information about environment.
  oref0 pebble
  oref0 ifttt-notify
  oref0 get-profile
  oref0 calculate-iob
  oref0 meal
  oref0 export-loop [backup-loop.json] - Print a backup json representation of
                                         entire configuration. Optionally, if a
                                         filename is specified, listing is
                                         saved in the file instead.
  oref0 help - this message
EOF

NAME=${1-help}
shift
PROGRAM="oref0-${NAME}"
COMMAND=$(which $PROGRAM | head -n 1)

case $NAME in
device-helper)
  name=$1
  shift
  cat <<EOF
{"$name": {"vendor": "openaps.vendors.process", "extra": "${name}.ini"}, "type": "device", "name": "$name", "extra": {"fields": "", "cmd": "bash", "args": "-c \"$*\" -- "}}

EOF
  ;;
alias-helper)
  name=$1
  shift
  cat <<EOF
{"type": "alias", "name": "$name", "$name": {"command": "! bash -c \"$*\" --"}}
EOF
  ;;
env)
  echo PATH=$PATH
  env
  exit
  ;;
export-loop)
  out=${1-/dev/stdout}
  openaps import -l | while read type ; do openaps $type show --json ; done | json -g > $out

  exit
  ;;
*)
  test -n "$COMMAND" && exec $COMMAND $*
  ;;
esac


