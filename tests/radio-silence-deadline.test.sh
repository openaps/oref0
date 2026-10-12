#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
exec 4>/dev/null
source <(sed -n '/^function wait_for_silence {/,/^}/p' "$repo_dir/bin/oref0-bash-common-functions.sh")
sleep() { SECONDS=$((SECONDS + 1)); }
date() { echo SYNTHETIC_TIME; }
timeout() {
    [[ "$1" =~ ^[0-9]+s$ && "$2" == listen ]]
    local remaining=${1%s}
    shift 2
    if [[ "$scenario" == hung ]]; then
        SECONDS=$((SECONDS + remaining))
        return 124
    fi
    listen "$@"
}
listen() {
    [[ "$1" == -t && "$2" == 27s ]]
    calls=$((calls + 1))
    SECONDS=$((SECONDS + 27))
    case "$scenario" in
        quiet) echo 'SYNTHETIC_TIME timeout' >&2; return 1 ;;
        busy) return 0 ;;
        clears) [[ "$calls" -eq 1 ]] && return 0; echo 'SYNTHETIC_TIME timeout' >&2; return 1 ;;
        error) return 2 ;;
        native_error) echo 'SYNTHETIC_TIME radio error' >&2; return 1 ;;
    esac
}
for scenario in quiet busy clears error native_error hung; do
    SECONDS=0
    calls=0
    result=0
    wait_for_silence 27 || result=$?
    if [[ "$scenario" == quiet || "$scenario" == clears ]]; then
        [[ "$result" == 0 ]]
    else
        [[ "$result" == 1 ]]
    fi
    [[ "$SECONDS" -le 90 ]]
    case "$scenario" in
        quiet) [[ "$calls" -eq 1 ]] ;;
        clears) [[ "$calls" -eq 2 ]] ;;
        busy) [[ "$calls" -eq 3 ]] ;;
        error) [[ "$calls" -eq 1 ]] ;;
        native_error) [[ "$calls" -eq 1 ]] ;;
        hung) [[ "$calls" -eq 0 ]] ;;
    esac
done
echo 'Radio silence deadline: 6 synthetic cases passed.'
