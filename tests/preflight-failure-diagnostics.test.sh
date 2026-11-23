#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -r "$test_dir"' EXIT
cd "$test_dir"
exec 3>/dev/null 4>/dev/null
source <(sed -n '/^function preflight {/,/^}/p' "$repo_dir/bin/oref0-pump-loop.sh")
check_model() {
    printf 'attempt\n' >> attempts.log
    if [[ "$test_case" == transient && $(wc -l < attempts.log) -eq 1 ]]; then return 7; fi
    if [[ "$test_case" == failure ]]; then return 7; fi
    printf '%s\n' "$test_model" > settings/model.json
}
for test_case in success transient failure unsupported legacy; do
    test_model=523
    case "$test_case" in unsupported) test_model=999 ;; legacy) test_model=512 ;; esac
    : > attempts.log
    status=0
    preflight > result.log || status=$?
    case "$test_case" in
        success|transient|legacy) [[ "$status" == 0 ]]; grep -q 'OK.' result.log ;;
        failure) [[ "$status" == 1 ]]; grep -q 'stage=model-read exit=7' result.log ;;
        unsupported) [[ "$status" == 1 ]]; grep -q 'stage=model-validation' result.log ;;
    esac
    case "$test_case" in transient|failure) [[ $(wc -l < attempts.log) -eq 2 ]] ;; *) [[ $(wc -l < attempts.log) -eq 1 ]] ;; esac
done
printf 'Preflight diagnostics: 5 synthetic cases passed.\n'
