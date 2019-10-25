#!/usr/bin/env bash

# Usage: killall-g command [seconds]
# Kill the named command and its entire process group, like "killall -g command"
# if a second argument is provided, works much like killall -g --older-than,
# and looks for processes older than the specified number of seconds
# works will bash scripts where killall doesn't (it only lets you killall running instances of bash)
# only  kills a single process group, the one with the highest PGID

if [[ -z "$2" ]]; then
    elapsed=0
else
    elapsed=$2
fi
ps x -O pgid,etimes | egrep -v "grep|killall" | grep $1 | tail -1 | awk '{if ($3 >= '$elapsed') print $2}'  | while read pgid; do kill -- -$pgid; done
