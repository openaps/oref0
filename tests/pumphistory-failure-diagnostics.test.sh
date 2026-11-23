#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -r "$test_dir"' EXIT
cd "$test_dir"
mkdir monitor
printf '.\n' > openaps.jq
exec 3>/dev/null
source <(sed -n '/^function read_pumphistory()/,/^}/p' "$repo_dir/bin/oref0-pump-loop.sh")
try_fail() { "$@"; }
read_full_pumphistory() { full_refresh_called=yes; return 0; }
pumphistory() {
    printf 'SYNTHETIC acquisition diagnostic\n' >&2
    printf '[]\n'
    return "$history_exit"
}
for history_exit in 0 1 2; do
    full_refresh_called=no
    printf '[{"id":"RECORD_EXAMPLE","timestamp":"2030-01-01T00:00:00Z"}]\n' > monitor/pumphistory-24h-zoned.json
    actual_exit=0
    read_pumphistory > result.log 2> error.log || actual_exit=$?
    if [[ "$history_exit" == 0 ]]; then
        [[ "$actual_exit" == 0 && "$full_refresh_called" == no ]]
        [[ ! -s error.log ]]
        [[ ! -e monitor/pumphistory-24h-zoned-old.json ]]
    elif [[ "$history_exit" == 1 ]]; then
        [[ "$actual_exit" == 1 && "$full_refresh_called" == no ]]
        [[ $(jq length monitor/pumphistory-24h-zoned.json) == 1 ]]
        grep -q 'Pump history refresh failed (exit 1)' error.log
        grep -q 'SYNTHETIC acquisition diagnostic' error.log
    else
        [[ "$actual_exit" == 0 && "$full_refresh_called" == yes ]]
        grep -q 'Pump history refresh failed (exit 2)' error.log
    fi
done
history_exit=0
full_refresh_called=no
printf 'INVALID_SYNTHETIC_FILTER(\n' > openaps.jq
printf '[{"id":"RECORD_EXAMPLE","timestamp":"2030-01-01T00:00:00Z"}]\n' > monitor/pumphistory-24h-zoned.json
actual_exit=0
read_pumphistory > result.log 2> error.log || actual_exit=$?
[[ "$actual_exit" != 0 && "$full_refresh_called" == no ]]
[[ $(jq length monitor/pumphistory-24h-zoned.json) == 1 ]]
grep -q 'compile error' error.log
printf 'Pump history failure diagnostics: 4 cases passed.\n'
