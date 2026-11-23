#!/usr/bin/env bash
set -eu
repo="$(cd "$(dirname "$0")/.." && pwd)"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/autotune-validation.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT
mkdir "$scratch/bin"
export TZ=UTC
export PATH="$scratch/bin:$PATH"
export NIGHTSCOUT_HOST=https://wrong.example.invalid

cat >"$scratch/bin/ns-get" <<'NODE'
#!/usr/bin/env node
const assert = require('assert');
const query = require('querystring').parse(process.argv[5]);
assert.strictEqual(process.argv[3], 'https://current.example.invalid');
assert.strictEqual(process.env.NIGHTSCOUT_HOST, process.argv[3]);
assert.strictEqual(process.env.NIGHTSCOUT_STRICT_READ, '1');
const testCase = process.env.AUTOTUNE_TEST_CASE;
if (process.argv[4] === 'entries/sgv.json') {
    const start = Number(query['find[date][$gte]']);
    const end = Number(query['find[date][$lte]']);
    const rows = [];
    for (let date = start; date < end; date += 300000) rows.push({date, sgv: 110});
    if (testCase === 'glucose-gap') {
        rows.splice(120, 12);
        rows[5].sgv = 0;
    }
    if (testCase === 'unusable-glucose') rows.forEach(row => { row.sgv = 0; });
    if (testCase === 'valid-glucose-string') {
        rows.forEach(row => { row.glucose = String(row.sgv); delete row.sgv; });
    }
    console.log(JSON.stringify(testCase === 'empty-glucose' ? [] : rows));
} else {
    const start = Date.parse(query['find[created_at][$gte]']);
    const end = Date.parse(query['find[created_at][$lte]']);
    const at = (start + end) / 2;
    const row = {created_at: new Date(at).toISOString(), eventType:'Correction Bolus', insulin: 1};
    if (testCase === 'empty' || (testCase === 'later-empty' && row.created_at.startsWith('2026-10-14'))) {
        console.log('[]');
    } else if (testCase === 'non-array') {
        console.log('{"status":401}');
    } else if (testCase === 'transport-error') {
        process.exit(22);
    } else if (testCase === 'out-of-window') {
        console.log(JSON.stringify([{created_at:'2020-01-01T00:00:00Z', insulin:1}]));
    } else if (testCase === 'neighboring-treatments-only') {
        console.log(JSON.stringify([{created_at:new Date(start).toISOString(), eventType:'Correction Bolus', insulin:1}]));
    } else if (testCase === 'carb-only') {
        console.log(JSON.stringify([{created_at:row.created_at, eventType:'Carb Correction', carbs:15}]));
    } else if (testCase === 'basal-only') {
        console.log(JSON.stringify([{created_at:row.created_at, eventType:'Temp Basal', rate:0, duration:30}]));
    } else if (testCase === 'cross-boundary-basal') {
        const basalAt = new Date(start + (22 * 60 - 5) * 60000).toISOString();
        console.log(JSON.stringify([{created_at:basalAt, eventType:'Temp Basal', rate:0, duration:30}]));
    } else if (testCase === 'notes-only') {
        console.log(JSON.stringify([{created_at:row.created_at, eventType:'Note', notes:'Synthetic treatment note'}]));
    } else if (testCase === 'at-response-cap') {
        console.log(JSON.stringify(Array(Number(query.count)).fill(row)));
    } else {
        console.log(JSON.stringify([row]));
    }
}
NODE
cat >"$scratch/bin/oref0-autotune-prep" <<'MOCK'
#!/usr/bin/env bash
touch "$AUTOTUNE_TEST_PREP"
printf '{}\n'
MOCK
cat >"$scratch/bin/oref0-autotune-core" <<'MOCK'
#!/usr/bin/env bash
printf '{"basalprofile":[{"start":"00:00:00","rate":1.2}]}\n'
MOCK
cat >"$scratch/bin/oref0-autotune-recommends-report" <<'MOCK'
#!/usr/bin/env bash
printf 'Synthetic report\n' >"$1/autotune/autotune_recommendations.log"
MOCK
chmod +x "$scratch/bin/"*
for test_case in empty non-array transport-error empty-glucose unusable-glucose out-of-window neighboring-treatments-only at-response-cap later-empty carb-only notes-only valid glucose-gap valid-glucose-string basal-only cross-boundary-basal; do
    run="$scratch/$test_case"
    mkdir -p "$run/settings" "$run/autotune"
    printf '{"basalprofile":[{"start":"00:00:00","rate":1.0}]}\n' >"$run/settings/pumpprofile.json"
    printf '{"basalprofile":[{"start":"00:00:00","rate":0.9}]}\n' >"$run/prior-profile.json"
    cp "$run/prior-profile.json" "$run/autotune/profile.json"
    cp "$run/prior-profile.json" "$run/settings/autotune.json"
    cp "$run/prior-profile.json" "$run/settings/profile.json"
    export AUTOTUNE_TEST_CASE="$test_case" AUTOTUNE_TEST_PREP="$run/prep-called"
    expect_success=false
    case "$test_case" in
        valid|glucose-gap|valid-glucose-string|basal-only|cross-boundary-basal) expect_success=true ;;
    esac
    if bash "$repo/bin/oref0-autotune.sh" --dir="$run" --ns-host=https://current.example.invalid \
        --start-date=2026-10-13 --end-date=2026-10-14 --log=false >"$run/log" 2>&1; then
        if [[ "$expect_success" == false ]]; then
            cat "$run/log" >&2
            printf 'Unexpected success: %s\n' "$test_case" >&2
            exit 1
        fi
        [[ -f "$run/prep-called" && -f "$run/autotune/newprofile.2026-10-14.json" ]]
    else
        if [[ "$expect_success" == true ]]; then
            cat "$run/log" >&2
            exit 1
        fi
        [[ ! -e "$run/prep-called" ]]
        for f in "$run/autotune/profile.json" "$run/settings/autotune.json" "$run/settings/profile.json"; do
            cmp "$f" "$run/prior-profile.json"
        done
    fi
    printf 'PASS %s\n' "$test_case"
done

# Also protect direct replay callers, which do not use the fetch wrapper.
printf '[]\n' >"$scratch/empty.json"
for inputs in missing-treatments missing-glucose carb-only; do
    history="$scratch/valid/autotune/ns-treatments.2026-10-13.json"
    glucose="$scratch/valid/autotune/ns-entries.2026-10-13.json"
    if [[ "$inputs" == missing-treatments ]]; then
        history="$scratch/empty.json"
    elif [[ "$inputs" == missing-glucose ]]; then
        glucose="$scratch/empty.json"
    else
        history="$scratch/carb-only.json"
        printf '[{"created_at":"2026-10-13T12:00:00Z","eventType":"Carb Correction","carbs":15}]\n' >"$history"
    fi
    if node "$repo/bin/oref0-autotune-prep.js" "$history" "$scratch/valid/settings/pumpprofile.json" \
        "$glucose" "$scratch/valid/settings/pumpprofile.json" >"$scratch/prep-log" 2>&1; then
        printf 'Direct replay accepted %s\n' "$inputs" >&2
        exit 1
    fi
    grep -Eq 'Autotune requires (nonempty|usable insulin history)' "$scratch/prep-log"
    printf 'PASS direct %s\n' "$inputs"
done

# Report mismatched cron and configured hosts before running Autotune.
mkdir "$scratch/nightly"
touch "$scratch/nightly/openaps.ini"
printf '{"enable":"autotune","nightscout_host":"https://current.example.invalid"}\n' \
    >"$scratch/nightly/preferences.json"
if (cd "$scratch/nightly" && bash "$repo/bin/oref0-cron-nightly.sh") >"$scratch/nightly/log" 2>&1; then
    printf 'Nightly Autotune accepted conflicting host settings\n' >&2
    exit 1
fi
grep -q 'preference and cron destination do not agree' "$scratch/nightly/log"
printf 'PASS mismatched Nightscout host\n'
