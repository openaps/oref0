#!/bin/echo This file should be source'd from another script, not run directly:
#
# Common functions for shell script components of oref0.

# Set $self to the name the currently-executing script was run as. This is usually
# used in help messages.
self=$(basename $0)

PREFERENCES_FILE="preferences.json"

function run_remote_command () {
    set -o pipefail
    out_file=$( mktemp /tmp/shared_node.XXXXXXXXXXXX)
    #echo $out_file
    echo -n $1 |socat -t90 - UNIX-CONNECT:/tmp/oaps_shared_node > $out_file || return 1
    #cat $out_file
    jq -j .err $out_file >&2
    jq -j .stdout $out_file 
    return_val=$( jq -r .return_val $out_file)
    rm $out_file
    return $(( return_val ))
}

function start_share_node_if_needed() {
    # First check if node is alive
    output="$(echo ping |socat -t90 - UNIX-CONNECT:/tmp/oaps_shared_node)"
    echo $output
    if [ "$output" = '{"err":"","stdout":"pong","return_val":0}' ]; then
        echo shared node is alive
        return 0
    fi
    echo 'killing node so it will restart later'
        node_pid="$(ps -ef | grep node | grep oref0-shared-node.js | grep -v grep | awk '{print $2 }')"
    echo $node_pid
    kill -9 $node_pid
    # Node should start automaticly by oref0-shared-node-loop
    # Waiting 90 seconds for it to start
    for i in {1..90}
    do
       sleep 1
       output="$(echo ping |socat -t90 - UNIX-CONNECT:/tmp/oaps_shared_node)"
       echo $output
       if [ "$output" = '{"err":"","stdout":"pong","return_val":0}' ]; then
           echo shared node is alive
           return 0
       fi
    done
    die Waiting for shared node failed 
}

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
    if getent passwd edison &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Returns success (0) if running on a Debian Jessie system, fail (1) otherwise
is_debian_jessie() {
    if cat /etc/os-release | grep 'PRETTY_NAME="Debian GNU/Linux 8 (jessie)"' &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Returns success (0) if running on a Raspberry Pi, fail (1) otherwise. Uses
# the existence of a "pi" account in /etc/passwd to determine that.
is_pi () {
    if getent passwd pi &> /dev/null; then
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

function mydate {
    if [[ `uname` == 'Darwin' || `uname` == 'FreeBSD' || `uname` == 'OpenBSD' ]] ; then
        gdate "$@"
    else
        date "$@"
    fi
}
# Output the number of seconds since epoch (Jan 1 1970).
epochtime_now () {
    mydate +%s
}

# Usage: to_epochtime <datetime>
# Convert a string representation of a datetime to a number of seconds since
# epoch. This is fairly resilient about argument format; it will ignore quotes
# and newlines, and the string can be spread across multiple arguments (so
# you don't need to quote the parameters to avoid word-splitting).
to_epochtime () {
    mydate -d "$(echo "$@" |tr -d '"\n')" +%s
}


# recieves a line of text and logger name and creates a line in the following format:
# timestamp logger-name message
# This function is needed in order to create a log file that will look like:
# 2019-01-27 02:13:15 openaps.pumploop Merging local temptargets: (NOT VALID JSON: empty) 
# This files can be read with programs like chainsaw.
adddate() {
    while IFS= read -r line; do
        echo "$(date  +"%Y-%m-%d %T") $1 $line"
    done
}

# Remove the color Escape sequences from the logs, since some programs can not read them, and have their own coloring rules.
uncolor () {
     while IFS= read -r line; do
        sed --expression="s/\o33\[[01]m//g" | 
        sed --expression="s/\o33\[[01];39m//g" |
        sed --expression="s/\o33\[[01];32m//g" |
        sed --expression="s/\o33\[34;1m//g"  |
        sed --expression="s/\o33\[1;30m//g" 
     done
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

# Usage: colorize_json [jq-selector]
# Take JSON on stdin, optionally apply a jq selector, and output a compact
# syntax-colored version of the results to stdout. If the input is not valid
# JSON, copy the input to the output unchanged, and also print
# "(NOT VALID JSON: <reason>)" at the end. Return success in any case.
colorize_json () {
    local INPUT="$(cat)"

    if [[ "$INPUT" == "" ]]; then
        echo "(NOT VALID JSON: empty)"
    else
        local COLORIZED_OUTPUT
        COLORIZED_OUTPUT="$(echo "$INPUT" |jq -C -c "${@-.}" 2>&1)"

        if [[ $? != 0 ]]; then
            # If jq returned failure, it also wrote an error message.
            echo "$INPUT (NOT VALID JSON: $(echo $COLORIZED_OUTPUT))"
        elif [[ "$COLORIZED_OUTPUT" == "" ]]; then
            # If the input was truncated-JSON, jq doesn't output anything and
            # returns success. But the empty string is not itself valid JSON, so
            # we can detect this.
            echo "$INPUT (NOT VALID JSON: unclosed quote, brace or bracket)"
        else
            echo "$COLORIZED_OUTPUT"
        fi
    fi
}

# Return success if the code that called this function was loaded with "source"
# or ".", false if it was run directly. Note that wrapping a call to this in a
# function changes it to refer to the location of the wrapping function.
# Used by oref0-log-shortcuts to determine whether to/whether it's possible to
# add aliases to the user's shell.
# https://stackoverflow.com/questions/2683279/how-to-detect-if-a-script-is-being-sourced
script_is_sourced () {
    [[ "${BASH_SOURCE[1]}" != "${0}" ]]
}


# Usage: prompt_yn <question> <default-value>
# Give the user (running the script in a terminal) a yes/no prompt. Return
# success if the the answer was yes, failure if the answer was no. If the user
# just presses Enter, the result is default-value (if given). If the answer is
# something other than yes or no, ask the question again.
prompt_yn () {
    while true; do
        if [[ "$2" =~ ^[Yy]$ ]]; then
            read -p "$1 [Y]/n " -r
        else
            read -p "$1 y/[N] " -r
        fi
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            return 0
        elif [[ "$REPLY" =~ ^[Nn]$ ]]; then
            return 1
        elif [[ $# -ge 2 ]]; then
            if [[ "$2" =~ ^[Yy]$ ]]; then
                return 0
            elif [[ "$2" =~ ^[Nn]$ ]]; then
                return 1
            else
                echo "Invalid default specified: $2"
            fi
        else
            echo "Please answer Y or N."
        fi
    done
}

# Usage: prompt_and_validate <variable> <question> <validation-function> <default-value>
#
# Give the user (running the script in a terminal) a prompt, check their reply
# by running validation-function, and store the result in the named variable.
#
# The validation function takes one parameter, which is the value the user
# entered, and returns success if it's valid, false otherwise. If validation
# fails, it should output something on stdout or stderr which explains why.
# To disable validation, pass "true" as the validation function (or omit the
# argument).
#
# If the user enters something other than the empty string which fails
# validation, and then they enter the exact same thing again, they will be
# asked whether they want to override the validator.
prompt_and_validate () {
    local VARNAME="$1"
    local QUESTION="$2"
    local VALIDATOR="${3-true}"
    local DEFAULT="$4"

    local LAST_VALUE=""

    while true; do
        if [[ $# -ge 4 ]]; then
            read -p "$QUESTION [$DEFAULT] " -r "$VARNAME"
        else
            read -p "$QUESTION " -r "$VARNAME"
        fi

        if [[ "${!VARNAME}" == "" ]]; then
            # User entered the empty string? Use the default value, if there is one.
            if [[ $# -ge 4 ]]; then
                export "$VARNAME"="$DEFAULT"
                return 0
            fi
        elif "$VALIDATOR" "${!VARNAME}"; then
            return 0
        elif [[ ! -z "${!VARNAME}" ]] && [[ "${!VARNAME}" == "$LAST_VALUE" ]]; then
            if prompt_yn "Override validation and use \"${!VARNAME}\"?" N; then
                return 0
            fi
        fi
        LAST_VALUE="${!VARNAME}"
    done
}


# Output the contents of preferences.json. (This is a function rather than just
# a varname that you cat(1) because of plans to make it support HJSON, which
# requires preprocessing and caching.
get_prefs_json () {
    cat "$PREFERENCES_FILE"
}

# Usage: get_pref_bool <preference-expr> [default-value]
#
# Check myopenaps/preferences.json for a setting matching preference-expr which
# is a bool. If it's present and is a bool, output it and return success. If
# the setting is missing or null but default-value is given, output
# default-value and return success.  If the setting is missing and there's no
# default value, the setting is present but isn't a boolean, the preferences
# file is missing or the preference file fails to parse, writes an error to
# stderr, writes false to stdout, and returns fail.
#
# Example:
#     MY_SETTING=$(get_pref_bool .my_boolean_setting) || die
#     if [[ $MY_SETTING == true ]]; then
#         echo Setting was true
#     fi
get_pref_bool () {
    set -e
    set -o pipefail
    RESULT="$(get_prefs_json |jq "$1")"
    if [[ "$RESULT" == "null" ]]; then
        if [[ "$2" != "" ]]; then
            echo "$2"
            return 0
        else
            echo "Undefined preference setting and no default provided for $1 in $PREFERENCES_FILE_ABSOLUTE" 1>&1
            return 1
        fi
    elif [[ "$RESULT" == "true" || "$RESULT" == "false" ]]; then
        echo "$RESULT"
        return 0
    else
        echo "Setting $1 in $PREFERENCES_FILE_ABSOLUTE should be a boolean, was $RESULT" 1>&2
        return 1
    fi
}

# Usage: check_pref_bool <preference-name> [default-value]
#
# Like get_pref_bool except that instead of outputting true or false, returns
# success for settings that are true and failure for settings that are false,
# and outputs nothing. If default-value is omitted, the default is false. If
# something is wrong (config file is missing or corrupt, value is not boolean),
# this will output a warning to stderr, but otherwise continue on with the
# default value.
#
# Example:
#     if check_pref_bool .my_boolean_setting; then
#         echo Setting was true
#     fi
check_pref_bool () {
    if [[ $(get_pref_bool "$@") == true ]]; then
        return 0
    else
        return 1
    fi
}

# Usage: string_is_number <string>
#
# Returns success if the argument is a number (possibly with a decimal component
# or scientific notation, but not NaN or Inf), failure otherwise.
string_is_number () {
    NUMBER_REGEX='^-?[0-9]+([.][0-9]*)?([Ee]-?[0-9]+)?$'
    if [[ "$1" =~ $NUMBER_REGEX ]]; then
        return 0
    else
        return 1
    fi
}

# Usage: get_pref_float <preference-name> [default-value]
#
# Check myopenaps/preferences.json for a setting matching preference-name which
# is a float. If it's present and is a number, output it and return success. If
# it's missing or null but default-value was given, output default-value
# instead. If the setting is missing and there's no default value, the setting
# is present but isn't a number, or the preferences file is missing or fails
# to parse, outputs 0, writes to stderr, and returns failure.
#
# Example:
#     THRESHOLD=$(get_pref_float .my_threshold) || die
#     if ((FOO<THRESHOLD)); then
#         echo FOO was below threshold
#     fi
get_pref_float () {
    RESULT="$(get_prefs_json |jq "$1")"
    if [[ "$RESULT" == "null" ]]; then
        if [[ "$2" != "" ]]; then
            echo "$2"
            return 0
        else
            echo "Undefined preference setting and no default provided for $1 in $PREFERENCES_FILE_ABSOLUTE" 1>&2
            return 1
        fi
    else
        if ! string_is_number "$RESULT"; then
            echo "Setting $1 in $PREFERENCES_FILE_ABSOLUTE should be a number, was $RESULT" 1>&2
            return 1
        else
            echo "$RESULT"
            return 0
        fi
    fi
}

# Usage: get_pref_string <preference-name> [default-value]
#
# Check myopenaps/preferences.json for a setting matching preference-name which
# is a string. If it's present but isn't a string, it'll be coerced to a string
# corresponding to its JSON serialization. If it's missing but default-value
# was given, outputs default-value. If it's missing and there's no default
# value, write a message to stderr and return failure.
#
# The output is an unescaped string and may contain spaces, newlines, and
# special characters, so quotes are required around invocations of this
# function and any variable that stores its result.
#
# Example:
#     USER_NICKNAME="$(get_pref_string .alert_text)" || die
#     echo "Hello, $USER_NICKNAME"
get_pref_string () {
    RESULT="$(get_prefs_json |jq --exit-status --raw-output "$1")"
    RETURN_CODE=$?

    if [[ $RETURN_CODE == 0 ]]; then
        echo "$RESULT"
        return 0
    elif [[ $# -ge 2 ]]; then
        echo "$2"
        return 0
    else
        echo "Failed to get string preference $1" 1>&2
        return 1
    fi
}

# Usage: set_pref_json <preference-name> <new-value>
# Change the value of something in preferences.json. The preference-name is
# given as a jq selector, typically ".pref_name"; the value should be JSON,
# including quotes if it's a string. (For setting strings you probably want
# set_pref_string which handles the string-escaping.)
set_pref_json () {
    if [[ -f "$PREFERENCES_FILE" ]]; then
        local OLD_PREFS="$(get_prefs_json)"
        local NEW_PREFS="$(echo "$OLD_PREFS" |jq "$1 |= $2")"
    else
        local NEW_PREFS="$(echo '{}' |jq "$1 |= $2")"
    fi

    # Write the whole file and move into place, so that the change is atomic
    echo "$NEW_PREFS" >"${PREFERENCES_FILE}.new"
    mv -f "${PREFERENCES_FILE}.new" "$PREFERENCES_FILE"
}

# Usage: set_pref_string <preference-name> <string-value>
set_pref_string () {
    # TODO: Escape quotes and backslashes
    set_pref_json "$1" "\"$2\""
}

dedupe_path() {
    #from https://unix.stackexchange.com/a/40973
    if [ -n "$PATH" ]; then
        old_PATH=$PATH:; PATH=
        while [ -n "$old_PATH" ]; do
            x=${old_PATH%%:*}       # the first remaining entry
            case $PATH: in
            *:"$x":*) ;;         # already there
            *) PATH=$PATH:$x;;    # not there yet
            esac
            old_PATH=${old_PATH#*:}
        done
        PATH=${PATH#:}
        unset old_PATH x
    fi
}

# Usage: wait_for_silence <seconds of silence>
# listen for $1 seconds of silence (no other rigs or enlite transmitter talking to pump) before continuing
# If communication is detected, it'll retry to listen for $1 seconds.
#
# returns 0 if radio is free, 1 if radio is jammed for 800 iterations.
function wait_for_silence {
    if [ -z $1 ]; then
        upto45s=$[ ( $RANDOM / 728 + 1) ]
        waitfor=$upto45s
    else
        waitfor=$1
    fi
    echo -n "Listening for ${waitfor}s: "
    for i in $(seq 1 800||gseq 1 800); do
        echo -n .
        # returns true if it hears pump comms, false otherwise
        if ! listen -t $waitfor's' 2>&4 ; then
            echo " All clear."
            echo -n "Continuing oref0-pump-loop at "; date
            return 0
        else
            sleep 1
        fi
    done
    return 1
}
