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
    
    # Tests go here
}

cleanup