#!/usr/bin/env bash

# Usage: killall-g command [seconds]
# Kill the named bash script and its entire process group, like "killall -g command"
# if a second argument is provided, works much like killall -g --older-than,
# and looks for processes older than the specified number of seconds
# works with bash scripts called via "bash script_name", which killall doesn't support
# (it only lets you killall based on the process name, which is just "bash"
# for non-bash scripts, you can specify a third argument to match against fname

script=$1
if [[ -z "$2" ]]; then
    older_than=0
else
    older_than=$2
fi
if [[ -z "$3" ]]; then
    process="bash"
else
    process=$3
fi
ps x -A -o pid,fname,etimes,pgid,args | egrep -v "grep|killall" | awk '$NF ~ /'$script'/' | while read pid fname etimes pgid args; do
    #echo pid $pid, args $args, fname $fname, pgid $pgid, etimes $etimes
    if [[ $fname == $process ]] && [ $etimes -ge $older_than ] && ps -p $pid > /dev/null; then
        pstree -a $pid
        echo killing $args pid $pid pgid $pgid running for $etimes seconds
        kill -- -$pgid
    fi;
done;
#ps x -O pgid,etimes | egrep -v "grep|killall" | grep $1 | tail -1 | awk '{if ($3 >= '$older_than') print $2}'  | while read pgid; do kill -- -$pgid; done
