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
    
    # Check that colorized_json handles invalid inputs correctly.
    if echo "{}" |colorize_json |grep 'NOT VALID JSON' >/dev/null; then
        fail_test "colorize_json reported an error on valid input"
    fi
    if ! echo "{" |colorize_json |grep 'NOT VALID JSON' >/dev/null; then
        fail_test "colorize_json didn't report an error on mismatched-curly-brace input"
    fi
    if ! echo "}" |colorize_json |grep 'NOT VALID JSON' >/dev/null; then
        fail_test "colorize_json didn't report an error on close-curly-brace input"
    fi

    # Test that getting config variables when the config-file is missing is
    # fatal
    rm -f preferences.json
    get_pref_bool .noConfigFile >/dev/null 2>&1 \
        && fail_test "Loading bool config var with no config file present"
    get_pref_bool .noConfigFile true >/dev/null 2>&1 \
        && fail_test "Loading bool config var with no config file present"

    get_pref_float .noConfigFile >/dev/null 2>&1 \
        && fail_test "Loading float config var with no config file present"
    get_pref_float .noConfigFile 123 >/dev/null 2>&1 \
        && fail_test "Loading float config var with no config file present"

    get_pref_string .noConfigFile >/dev/null 2>&1 \
        && fail_test "Loading string config var with no config file present"

    # Make a fake preferences.json to test the getters that extract values from it
    cat >preferences.json <<EOT
        {
            "bool_true": true,
            "bool_false": false,
            "number_5": 5,
            "number_3_5": 3.5,
            "number_big": 1.1e99,
            "string_hello": "hello",
            "null_value": null
        }
EOT

    # Test boolean getter
    if ! check_pref_bool .bool_true; then
        fail_test "Wrong result for check_pref_bool on a true value"
    fi
    if check_pref_bool .bool_false; then
        fail_test "Wrong result for check_pref_bool on a false value"
    fi
    if check_pref_bool .missing false; then
        fail_test "Wrong result for check_pref_bool on a missing value with default false"
    fi
    if ! check_pref_bool .missing true; then
        fail_test "Wrong result for check_pref_bool on a missing value with default true"
    fi
    
    # Test numeric getter
    if [ "$(get_pref_float .number_5)" -ne "5" ]; then
        fail_test "Wrong result for get_pref_float on an integer value"
    fi
    if [ "$(get_pref_float .number_3_5)" != "3.5" ]; then
        fail_test "Wrong result for get_pref_float on a non-integer value"
    fi
    if [ "$(get_pref_float .missing 123)" -ne 123 ]; then
        fail_test "Wrong result for get_pref_float on a missing value with default specified"
    fi
    
    # Test string getter
    if [ "$(get_pref_string .string_hello)" != "hello" ]; then
        fail_test "Wrong result for get_pref_string"
    fi
    if [ "$(get_pref_string .missing stringDefault)" != "stringDefault" ]; then
        fail_test "Wrong result for get_pref_string on a missing value with default"
    fi
    
    # Test mutating a (non-empty) config file to add a new setting
    set_pref_json .mutated_pref 123
    if [ "$(get_pref_float .mutated_pref)" != 123 ]; then
        fail_test "set_pref_json didn't set a pref correctly"
    fi
    
    # Test mutating a config file to change an existing setting
    set_pref_json .mutated_pref 567
    if [ "$(get_pref_float .mutated_pref)" != 567 ]; then
        fail_test "set_pref_json didn't mutate a pref correctly"
    fi
    
    # Test mutating an (empty) config file
    rm -f preferences.json
    set_pref_json .empty_mutated_pref 123
    if [ "$(get_pref_float .empty_mutated_pref)" != 123 ]; then
        fail_test "set_pref_json didn't set a pref correctly when config file was empty"
    fi
    
    # Test mutating a config file, adding a quoted string
    set_pref_string .mutated_pref Hello
    if [ "$(get_pref_string .mutated_pref)" != "Hello" ]; then
        fail_test "set_pref_string didn't set a string pref correctly"
    fi

    # Test script_is_sourced
    TEST_SCRIPT="$(cat <<EOT
#!/bin/bash
source ../bin/oref0-bash-common-functions.sh
if script_is_sourced; then
    echo sourced
else
    echo executed
fi
EOT
    )"
    echo "$TEST_SCRIPT" >test_script_is_sourced.sh
    chmod +x test_script_is_sourced.sh
    if [[ "$(./test_script_is_sourced.sh)" != "executed" ]]; then
        fail_test "script_is_sourced on executed script"
    fi
    if [[ "$(source ./test_script_is_sourced.sh)" != "sourced" ]]; then
        fail_test "script_is_sourced on sourced script"
    fi
    
    # Test oref0-log-shortcuts
    cat >test_bash_profile <<EOT
This line doesn't get removed

The line below this should be removed
alias networklog="tail -n 100 -F /var/log/openaps/network.log"
The line above this should be removed

EOT
    EXPECTED_NEW_PROFILE="$(cat <<EOT
This line doesn't get removed

The line below this should be removed
The line above this should be removed

source "$(readlink -f ../bin/oref0-log-shortcuts.sh)"
source /etc/skel/.profile
EOT
    )"
    ../bin/oref0-log-shortcuts.sh --add-to-profile=./test_bash_profile
    if [[ "$(cat test_bash_profile)" != "$(echo "$EXPECTED_NEW_PROFILE")" ]]; then
        echo "Actual: $(cat test_bash_profile)"
        echo "Expected: $(echo "$EXPECTED_NEW_PROFILE")"
        fail_test "oref0-log-shortcuts did not modify test_bash_profile correctly"
    fi
}

cleanup
