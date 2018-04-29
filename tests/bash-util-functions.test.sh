#!/bin/bash

source bin/oref0-bash-common-functions.sh

fail_test () {
    echo "$@" 1>&2
    exit 1
}

ORIGINAL_PWD="$PWD"
cleanup () {
    cd "$ORIGINAL_PWD"
    if [ -d bash-unit-test-temp ]; then
        rm -rf bash-unit-test-temp
    fi
}

mkdir bash-unit-test-temp
{
    cd bash-unit-test-temp
    
    if [[ "$(echo -n '"x"' |noquotes)" != "x" ]]; then
        fail_test "noquotes gave wrong result"
    fi
    if [[ "$(echo -e 'x\n' |nonl)" != "x" ]]; then
        fail_test "nonl gave wrong result"
    fi
    
    
    if [[ $(to_epochtime "1970-01-01 00:01:00+000") != 60 ]]; then
        fail_test "to_epochtime gave incorrect result"
    fi
    if [[ $(to_epochtime 1970-01-01 00:01:00+000) != 60 ]]; then
        fail_test "to_epochtime seems to require its arguments to be quoted"
    fi
    if [[ $(to_epochtime 1970-01-01 00:01:00+000 + 1 second) != 61 ]]; then
        fail_test "to_epochtime doesn't do arithmetic"
    fi
}

cleanup