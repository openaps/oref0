#!/bin/bash

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/pumphistory-atomic-refresh-test.XXXXXX") \
    || exit 1

fail_test() {
    printf '%s\n' "$*" >&2
    exit 1
}

cleanup() {
    rm -rf "$TEST_ROOT"
}

trap cleanup EXIT

function_source=$(
    sed -n \
        '/^function read_full_pumphistory()/,/^function read_bg_targets()/p' \
        "$REPO_ROOT/bin/oref0-pump-loop.sh" |
        sed '$d'
)
eval "$function_source"

read_pumphistory_source=$(
    sed -n \
        '/^function read_pumphistory()/,/^function compare_with_fullhistory()/p' \
        "$REPO_ROOT/bin/oref0-pump-loop.sh" |
        sed '$d'
)
eval "$read_pumphistory_source"

new_case() {
    local name="$1"
    CASE_DIR="$TEST_ROOT/$name"
    rm -rf "$CASE_DIR"
    mkdir -p "$CASE_DIR/monitor"
    printf '.\n' > "$CASE_DIR/openaps.jq"
    cd "$CASE_DIR" || fail_test "Unable to enter $CASE_DIR"
    exec 3>/dev/null
    exec 4>/dev/null
}

write_old_history() {
    printf '%s\n' '[{"timestamp":"old","_type":"Old"}]' \
        > monitor/pumphistory-24h-zoned.json
    chmod 0644 monitor/pumphistory-24h-zoned.json
}

assert_old_history() {
    printf '%s\n' '[{"timestamp":"old","_type":"Old"}]' > expected-old.json
    cmp -s expected-old.json monitor/pumphistory-24h-zoned.json \
        || fail_test "$1 replaced the existing history"
}

assert_no_candidate() {
    local candidate
    candidate=$(find monitor -maxdepth 1 \
        -name '.pumphistory-24h-zoned.json.new.*' -print -quit)
    [ -z "$candidate" ] || fail_test "$1 left candidate file $candidate"
}

file_mode() {
    stat -c %a "$1" 2>/dev/null || stat -f %Lp "$1"
}

test_success_replaces_history() (
    new_case success
    write_old_history

    pumphistory() {
        printf '%s\n' '[{"timestamp":"2026-07-17T15:00:00-08:00","_type":"TempBasal"}]'
    }

    read_full_pumphistory > refresh.log \
        || fail_test "Successful refresh returned failure"

    printf '%s\n' '[{"timestamp":"2026-07-17T15:00:00-08:00","_type":"TempBasal"}]' \
        | jq -f openaps.jq > expected-new.json
    cmp -s expected-new.json monitor/pumphistory-24h-zoned.json \
        || fail_test "Successful refresh did not install exact pipeline output"
    [ "$(file_mode monitor/pumphistory-24h-zoned.json)" = 644 ] \
        || fail_test "Successful refresh did not preserve mode 0644"
    grep -qx \
        'Full history refreshed through 2026-07-17T15:00:00-08:00' \
        refresh.log \
        || fail_test "Successful refresh changed operator log output"
    assert_no_candidate "Successful refresh"
)

test_restrictive_umask_is_preserved() (
    new_case restrictive-umask
    write_old_history
    umask 0077

    pumphistory() {
        printf '%s\n' '[{"timestamp":"new","_type":"TempBasal"}]'
    }

    read_full_pumphistory > refresh.log \
        || fail_test "Restrictive-umask refresh returned failure"

    [ "$(file_mode monitor/pumphistory-24h-zoned.json)" = 600 ] \
        || fail_test "Refresh did not preserve umask-derived mode 0600"
    assert_no_candidate "Restrictive-umask refresh"
)

test_read_only_umask_is_applied_after_write() (
    new_case read-only-umask
    write_old_history
    umask 0222

    pumphistory() {
        printf '%s\n' '[{"timestamp":"new","_type":"TempBasal"}]'
    }

    read_full_pumphistory > refresh.log \
        || fail_test "Read-only-umask refresh returned failure"

    [ "$(file_mode monitor/pumphistory-24h-zoned.json)" = 444 ] \
        || fail_test "Refresh did not preserve umask-derived mode 0444"
    assert_no_candidate "Read-only-umask refresh"
)

test_upstream_failure_preserves_history() (
    new_case upstream-failure
    write_old_history

    pumphistory() {
        printf '%s\n' '[{"timestamp":"partial","_type":"TempBasal"}]'
        return 42
    }

    if read_full_pumphistory > refresh.log; then
        fail_test "Upstream failure returned success"
    fi

    assert_old_history "Upstream failure"
    grep -qx 'Full history refresh failed. ' refresh.log \
        || fail_test "Upstream failure changed operator log output"
    assert_no_candidate "Upstream failure"
)

test_jq_failure_preserves_history() (
    new_case jq-failure
    write_old_history
    printf '., error("forced jq failure")\n' > openaps.jq

    pumphistory() {
        printf '%s\n' '[{"timestamp":"new","_type":"TempBasal"}]'
    }

    if read_full_pumphistory > refresh.log; then
        fail_test "jq failure returned success"
    fi

    assert_old_history "jq failure"
    assert_no_candidate "jq failure"
)

test_rename_failure_preserves_history() (
    new_case rename-failure
    write_old_history

    pumphistory() {
        printf '%s\n' '[{"timestamp":"new","_type":"TempBasal"}]'
    }
    mv() {
        return 1
    }

    if read_full_pumphistory > refresh.log; then
        fail_test "Rename failure returned success"
    fi

    assert_old_history "Rename failure"
    assert_no_candidate "Rename failure"
)

test_destination_directory_is_not_reported_as_success() (
    new_case destination-directory
    mkdir monitor/pumphistory-24h-zoned.json

    pumphistory() {
        printf '%s\n' '[{"timestamp":"new","_type":"TempBasal"}]'
    }

    if read_full_pumphistory > refresh.log; then
        fail_test "Destination-directory refresh returned success"
    fi

    [ -d monitor/pumphistory-24h-zoned.json ] \
        || fail_test "Destination-directory refresh changed the destination"
    [ -z "$(find monitor/pumphistory-24h-zoned.json -mindepth 1 -print -quit)" ] \
        || fail_test "Destination-directory refresh moved the candidate into the directory"
    assert_no_candidate "Destination-directory refresh"
)

test_failure_without_history_creates_no_live_file() (
    new_case missing-history

    pumphistory() {
        printf '%s\n' '[{"timestamp":"partial","_type":"TempBasal"}]'
        return 42
    }

    if read_full_pumphistory > refresh.log; then
        fail_test "Missing-history failure returned success"
    fi

    [ ! -e monitor/pumphistory-24h-zoned.json ] \
        || fail_test "Failure created a live history file where none existed"
    assert_no_candidate "Missing-history failure"
)

test_incremental_fallback_failure_remains_fail_closed() (
    new_case incremental-fallback-failure
    printf '%s\n' '[{"timestamp":"old","id":"old-id","_type":"Old"}]' \
        > monitor/pumphistory-24h-zoned.json
    chmod 0644 monitor/pumphistory-24h-zoned.json

    try_fail() {
        "$@"
    }
    pumphistory() {
        if [ "${1:-}" = "-f" ]; then
            return 2
        fi
        printf '%s\n' '[{"timestamp":"partial","_type":"TempBasal"}]'
        return 42
    }

    if read_pumphistory > refresh.log; then
        fail_test "Failed incremental fallback returned success"
    fi

    [ ! -e monitor/pumphistory-24h-zoned.json ] \
        || fail_test "Failed incremental fallback left suspect canonical history live"
    printf '%s\n' '[{"timestamp":"old","id":"old-id","_type":"Old"}]' \
        > expected-old.json
    cmp -s expected-old.json monitor/pumphistory-24h-zoned-old.json \
        || fail_test "Failed incremental fallback changed the known-good backup"
    assert_no_candidate "Failed incremental fallback"
)

test_incremental_fallback_success_installs_full_history() (
    new_case incremental-fallback-success
    printf '%s\n' '[{"timestamp":"old","id":"old-id","_type":"Old"}]' \
        > monitor/pumphistory-24h-zoned.json
    chmod 0644 monitor/pumphistory-24h-zoned.json

    try_fail() {
        "$@"
    }
    pumphistory() {
        if [ "${1:-}" = "-f" ]; then
            return 2
        fi
        printf '%s\n' '[{"timestamp":"new","id":"new-id","_type":"TempBasal"}]'
    }

    read_pumphistory > refresh.log \
        || fail_test "Successful incremental fallback returned failure"

    printf '%s\n' '[{"timestamp":"new","id":"new-id","_type":"TempBasal"}]' \
        | jq -f openaps.jq > expected-new.json
    cmp -s expected-new.json monitor/pumphistory-24h-zoned.json \
        || fail_test "Successful incremental fallback did not install full history"
    printf '%s\n' '[{"timestamp":"old","id":"old-id","_type":"Old"}]' \
        > expected-old.json
    cmp -s expected-old.json monitor/pumphistory-24h-zoned-old.json \
        || fail_test "Successful incremental fallback changed the prior backup"
    assert_no_candidate "Successful incremental fallback"
)

test_concurrent_readers_see_complete_history() (
    new_case concurrent-readers
    write_old_history

    pumphistory() {
        printf '%s\n' '[{"timestamp":"new","_type":"TempBasal"}]'
    }
    jq() {
        if [ "${1:-}" = "-f" ]; then
            cat >/dev/null
            printf '%s' '[{"timestamp":'
            sleep 0.2
            printf '%s\n' '"new","_type":"TempBasal"}]'
        else
            command jq "$@"
        fi
    }

    read_full_pumphistory > refresh.log &
    refresh_pid=$!

    while kill -0 "$refresh_pid" 2>/dev/null; do
        observed=$(cat monitor/pumphistory-24h-zoned.json)
        case "$observed" in
            '[{"timestamp":"old","_type":"Old"}]'|\
            '[{"timestamp":"new","_type":"TempBasal"}]')
                ;;
            *)
                fail_test "Concurrent reader observed partial history: $observed"
                ;;
        esac
    done

    wait "$refresh_pid" || fail_test "Concurrent refresh returned failure"
    assert_no_candidate "Concurrent refresh"
)

cleanup
mkdir -p "$TEST_ROOT"

test_success_replaces_history || exit 1
test_restrictive_umask_is_preserved || exit 1
test_read_only_umask_is_applied_after_write || exit 1
test_upstream_failure_preserves_history || exit 1
test_jq_failure_preserves_history || exit 1
test_rename_failure_preserves_history || exit 1
test_destination_directory_is_not_reported_as_success || exit 1
test_failure_without_history_creates_no_live_file || exit 1
test_incremental_fallback_failure_remains_fail_closed || exit 1
test_incremental_fallback_success_installs_full_history || exit 1
test_concurrent_readers_see_complete_history || exit 1

printf '%s\n' "pumphistory atomic refresh tests passed"
