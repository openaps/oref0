#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -r "$test_dir"' EXIT
cd "$test_dir"
mkdir monitor
exec 4>/dev/null
source <(sed -n '/^function check_tempbasal()/,/^}/p' "$repo_dir/bin/oref0-pump-loop.sh")
mdt() {
    [[ "$1" == tempbasal ]]
    printf '%s\n' "$test_response"
    if [[ "$test_exit" != 0 ]]; then printf 'SYNTHETIC radio error\n' >&2; fi
    return "$test_exit"
}
for test_case in success radio parser relative; do
    test_exit=0
    test_response='{"temp":"absolute"}'
    case "$test_case" in
        radio) test_exit=1; test_response='' ;;
        parser) test_response='invalid synthetic JSON' ;;
        relative) test_response='{"temp":"relative"}' ;;
    esac
    printf '{"previous":"SYNTHETIC"}\n' > monitor/last_temp_basal.json
    actual_exit=0
    check_tempbasal > result.log 2> error.log || actual_exit=$?
    if [[ "$test_case" == success ]]; then
        [[ "$actual_exit" == 0 && ! -s error.log ]]
        [[ $(jq -r .temp monitor/last_temp_basal.json) == absolute ]]
    else
        [[ "$actual_exit" != 0 ]]
        [[ $(jq -r .previous monitor/last_temp_basal.json) == SYNTHETIC ]]
        grep -q 'Pump temp basal read failed' error.log
        if [[ "$test_case" == radio ]]; then grep -q 'SYNTHETIC radio error' error.log; fi
        if [[ "$test_case" == parser ]]; then grep -q 'parse error' error.log; fi
    fi
done
printf 'Temp basal failure diagnostics: 4 cases passed.\n'
