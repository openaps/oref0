#!/bin/echo This file should be source'd from another script, not run directly:
#
# Common functions for shell script components of oref0.

# Set $self to the name the currently-executing script was run as. This is usually
# used in help messages.
self=$(basename $0)

PREFERENCES_FILE="preferences.json"


function overtemp {
    # check for CPU temperature above 85°C
    if is_pi; then
        TEMPERATURE=`cat /sys/class/thermal/thermal_zone0/temp`
        TEMPERATURE=`echo -n ${TEMPERATURE:0:2}; echo -n .; echo -n ${TEMPERATURE:2}`
        echo $TEMPERATURE | awk '$NF > 70' | grep input \
        && echo Rig is too hot: waiting for it to cool down at $(date)\
        && echo Please ensure rig is properly ventilated
    else
        sensors -u 2>/dev/null | awk '$NF > 85' | grep input \
        && echo Rig is too hot: waiting for it to cool down at $(date)\
        && echo Please ensure rig is properly ventilated
    fi
}

function highload {
    # check whether system load average is high
    uptime | tr -d ',' | awk "\$(NF-2) > 4" | grep load
}


die() {
    echo "$@"
    exit 1
}



# Takes a copy of the overall-program's arguments as arguments, and usage text
# as stdin. If the first argument is help, -h, or --help, print usage
# information and exit with status 0 (success). Otherwise, save the usage
# information in environment variable HELP_TEXT so it can be used by print_usage
# later.
#
# Correct invocation would look like:
#    usage "$@" <<EOT
#    Usage: $(basename $0) [--some-argument] [--some-other-argument]
#    Description of what this tool does. Information about what the arguments do.
#    EOT
usage () {
    case "$1" in
        help|-h|--help)
            cat -
            exit 0
            ;;
    esac
    export HELP_TEXT=$(cat -)
}

# Print the program's help text, as previously set by usage(). This would
# typically be used after detecting invalid arguments, and followed by "exit 1".
print_usage () {
    echo "$HELP_TEXT"
}

# Check that the current working directory contains openaps.ini, ie, is an
# OpenAPS session directory. This is presumably the myopenaps directory (though
# in principle it could also be ~/myopenaps-cgm-loop or something not part of
# the standard install). If it isn't, print a message saying it should be run
# from ~/myopenaps to stderr and exit with status 1 (failure).
assert_cwd_contains_ini () {
    if [[ ! -e "openaps.ini" ]]; then
        echo "$self: This script should be run from the myopenaps directory, but was run from $PWD which does not contain openaps.ini." 1>&2
        exit 1
    fi
}


# Returns success (0) if running on an Intel Edison, fail (1) otherwise. Uses
# the existence of an "edison" account in /etc/passwd to determine that.
is_edison () {
    #if egrep -i "edison" /etc/passwd 2>/dev/null; then
    if getent passwd edison; then
        return 0
    else
        return 1
    fi
}

# Returns success (0) if running on a Raspberry Pi, fail (1) otherwise. Uses
# the existence of a "pi" account in /etc/passwd to determine that.
is_pi () {
    if getent passwd pi > /dev/null; then
        return 0
    else
        return 1
    fi
}

# Usage: file_is_recent <path> <minutes>
# Return success if the modification time of the file at the given path has a
# modification time newer than the given number of minutes (default 5). Returns
# failure if the file doesn't exist, or is old.
file_is_recent () {
    BASE_NAME="$(basename $1)"
    find "$(dirname $1)" -mmin -"${2-5}" -name "$BASE_NAME" |grep -q "$BASE_NAME" >/dev/null 2>&1
    return $?
}

# Usage: file_is_recent_and_min_size <path> <minutes> <bytes>
# Return success if the modification time of the file at the given path has a
# modification time newer than the given number of minutes (default 5) *and* is
# at least the given number of bytes (default 5). The minimum size is chosen
# to exclude files like "{}\n" but include just about everything else. Returns
# failure if the file doesn't exist, is too small, or is old.
file_is_recent_and_min_size () {
    BASE_NAME="$(basename $1)"
    find "$(dirname $1)" -mmin -"${2-5}" -name "$BASE_NAME" -size +${3-5}c |grep -q "$BASE_NAME" >/dev/null 2>&1
    return $?
}

# Output the number of seconds since epoch (Jan 1 1970).
epochtime_now () {
    date +%s
}

# Usage: to_epochtime <datetime>
# Convert a string representation of a datetime to a number of seconds since
# epoch. This is fairly resilient about argument format; it will ignore quotes
# and newlines, and the string can be spread across multiple arguments (so
# you don't need to quote the parameters to avoid word-splitting).
to_epochtime () {
    date -d "$(echo "$@" |tr -d '"\n')" +%s
}

# Filter input to output, removing any embedded newlines.
# Example:
#     FOO="$(some_complex_thing |nonl)"
nonl () {
    tr -d '\n'
}

# Filter input to output, removing any quotes.
# Example:
#     FOO="$(some_complex_thing |noquotes)"
noquotes () {
    tr -d '"'
}

