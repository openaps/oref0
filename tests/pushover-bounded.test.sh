#!/usr/bin/env bash
set -euo pipefail

source bin/oref0-bash-common-functions.sh

# Stub only the process runner; exercise the production notification helper.
# No real notifications, network requests, or therapy records are used.
timeout () {
    [[ "$#" -eq 5 ]]
    [[ "$1" == "--kill-after=5s" && "$2" == "20s" ]]
    [[ "$3" == "oref0-pushover" ]]
    [[ "$4" == "TOKEN_EXAMPLE" && "$5" == "USER_EXAMPLE" ]]
    return "$test_notification_status"
}

for test_notification_status in 0 1 124 137 127; do
    test_output=$(run_optional_pushover TOKEN_EXAMPLE USER_EXAMPLE)
    case "$test_notification_status" in
        0) [[ -z "$test_output" ]] ;;
        124|137) [[ "$test_output" == *"notification timed out"* ]] ;;
        *) [[ "$test_output" == *"notification failed"* ]] ;;
    esac
    [[ "$test_output" != *TOKEN_EXAMPLE* && "$test_output" != *USER_EXAMPLE* ]]
done

# The pump loop must call the bounded helper, never the notifier directly.
grep -q 'run_optional_pushover "$PUSHOVER_TOKEN" "$PUSHOVER_USER"' bin/oref0-pump-loop.sh
! grep -q '^[[:space:]]*oref0-pushover ' bin/oref0-pump-loop.sh
echo "Bounded optional notification tests passed."
