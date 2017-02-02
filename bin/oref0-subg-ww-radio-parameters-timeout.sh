#!/bin/sh
# based on http://unix.stackexchange.com/questions/58304/is-there-a-way-to-call-a-command-with-a-set-time-limit-and-kill-it-when-that-tim

timeout_f () {
   echo running $1 for max $2 seconds
    $1 &
    sleep $2
    kill $! # ends somecommand if still running
}

timeout_f '/usr/local/bin/oref0-subg-ww-radio-parameters' 30 && #need 2 &'s
echo "forked.." # happens immediately

