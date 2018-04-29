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
    
    touch --date="3 minutes ago" file_3minsago
    touch --date="7 minutes ago" file_7minsago
    echo "123456789" >nonempty_file_3minsago
    echo "123456789" >nonempty_file_7minsago
    touch --date="3 minutes ago" nonempty_file_3minsago
    touch --date="7 minutes ago" nonempty_file_7minsago
    
    # Simple cases of file_is_recent
    if file_is_recent file_7minsago; then
        fail_test "file_is_recent returned success on an old file"
    fi
    if file_is_recent nonexistentfile; then
        fail_test "file_is_recent returned success on a non-existent file"
    fi
    if ! file_is_recent file_3minsago; then
        fail_test "file_is_recent returned fail on a recent file"
    fi
    
    # file_is_recent_and_min_size should care about whether files are empty
    if file_is_recent_and_min_size file_3minsago; then
        fail_test "file_is_recent_and_min_size returned success on an empty file"
    fi
    if ! file_is_recent_and_min_size nonempty_file_3minsago; then
        fail_test "file_is_recent_and_min_size returned fail on a nonempty file"
    fi
    
    # file_is_recent should not output to stdout or stderr, regardless of
    # whether it finds a match
    if [[ "$(file_is_recent nonexistentfile 2>&1)" != "" ]]; then
        fail_test "file_is_recent had output (when the file didn't exist)"
    fi
    if [[ "$(file_is_recent file_3minsago 2>&1)" != "" ]]; then
        fail_test "file_is_recent had output (when the file existed)"
    fi
}

cleanup