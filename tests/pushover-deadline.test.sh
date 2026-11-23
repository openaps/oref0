#!/usr/bin/env bash
set -euo pipefail

source bin/oref0-bash-common-functions.sh
export PATH="$PWD/tests/fixtures/pushover-hang:$PATH"
test_notification_started=$SECONDS
test_notification_output=$(run_optional_pushover TOKEN_EXAMPLE USER_EXAMPLE)
test_notification_elapsed=$((SECONDS - test_notification_started))
[[ "$test_notification_output" == *"notification timed out"* ]]
[[ "$test_notification_elapsed" -ge 20 && "$test_notification_elapsed" -le 30 ]]
echo "Hanging notification bounded; pump-loop continuation returned successfully."
