#!/bin/bash


self=$(basename $0)
MAX_IOB=${1-}
OUTPUT=${2-/dev/fd/1}
shift

function help_message ( ) {
  cat <<EOF
  Usage:
$self max_iob <max_iob> [max_iob.json]

$self help - this message
Print a perfect max_iob.json.


Examples:
$ $self 2
{
  "max_iob": 2
}

$ $self 2 foo.json
max_iob 2 saved in foo.json
bewest@hither:~/src/openaps/oref0$ 


EOF
}

case $MAX_IOB in
""| help)
  help_message
  ;;
*)
  cat <<EOF | json > $OUTPUT
{ "max_iob": $MAX_IOB }
EOF
  test "$OUTPUT" != '/dev/fd/1' && echo "max_iob $MAX_IOB saved in $OUTPUT"
  ;;
esac


