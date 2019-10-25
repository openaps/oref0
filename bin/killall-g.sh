#!/usr/bin/env bash

# Usage: killall-g command
# Kill the named command and its entire process group, like "killall -g command"
# works will bash scripts where killall doesn't (it only lets you killall running instances of bash)
# only  kills a single process group, the one with the highest PGID

ps x -o  "%p %r %a" | grep -v grep | grep $1 | tail -1 | awk '{print $2}' | while read pgid; do kill -- -$pgid; done
