#!/bin/bash

source bin/oref0-bash-common-functions.sh

fail_test () {
    printf "$@\n" 1>&2
    exit 1
}

ORIGINAL_PWD="$PWD"
cleanup () {
    cd "$ORIGINAL_PWD"
    [ -d bash-unit-test-temp ] && rm -rf bash-unit-test-temp
}

main () {
    mkdir -p bash-unit-test-temp || fail_test "Unable to create temporary directory"

    cd bash-unit-test-temp

    generate_test_files

    test-ns-status

    test-autotune-core

    test-autotune-prep

    test-calculate-iob

    test-detect-sensitivity

    test-determine-basal

    test-find-insulin-uses

    test-get-profile

    test-html

    test-meal

    test-normalize-temps

    test-raw

    test-set-local-temptarget

    cleanup
}

test-ns-status () {
    # Run ns-status and capture output
    ../bin/ns-status.js clock-zoned.json iob.json suggested.json enacted.json battery.json reservoir.json status.json 2>stderr_output 1>stdout_output

    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "ns-status error: \n$ERROR_LINES"

    # Make sure output has accurate clock data
    cat stdout_output | jq .pump.clock | grep -q "2018-09-05T09:44:11-05:00" || fail_test "ns-status reported incorrect clock value"

    # Make sure output has iob
    cat stdout_output | jq ".openaps.iob.iob" | grep -q -e "-0\.154" || fail_test "ns-status reported incorrect iob value"

    # Make sure output has suggested data
    cat stdout_output | jq ".openaps.suggested.deliverAt" | grep -q "2018-09-05T14:52:02.138Z" || fail_test "ns-status reported incorrect suggested deliverAt value"

    # Make sure output has enacted data
    cat stdout_output | jq ".openaps.enacted.deliverAt" | grep -q "2018-09-05T14:52:02.138Z" || fail_test "ns-status reported incorrect suggested deliverAt value"

    # Make sure output has battery data
    cat stdout_output | jq ".pump.battery.voltage" | grep -q 1.56 || fail_test "ns-status reported incorrect pump battery value."

    # Make sure output has pump reservoir data
    cat stdout_output | jq ".pump.reservoir" | grep -q 51.05 || fail_test "ns-status reported incorrect pump reservoir value."

    # Make sure output has status data
    cat stdout_output | jq ".pump.status.bolusing" | grep -q true || fail_test "ns-status reported incorrect pump status value."

    # Run ns-status with mmtune information and capture output
    ../bin/ns-status.js clock-zoned.json iob.json suggested.json enacted.json battery.json reservoir.json status.json mmtune.json 2>stderr_output 1>stdout_output

    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "ns-status error: \n$ERROR_LINES"

    # Make sure output has mmtune data
    cat stdout_output | jq ".mmtune.scanDetails | first | first" | grep -q 916.6 || fail_test "ns-status reported incorrect mmtune status value."

    # Run ns-status with uploader option and capture output
    ../bin/ns-status.js clock-zoned.json iob.json suggested.json enacted.json battery.json reservoir.json status.json --uploader uploader.json 2>stderr_output 1>stdout_output

    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "ns-status error: \n$ERROR_LINES"

    # Make sure output has uploader data
    cat stdout_output | jq ".uploader.battery" | grep -q 50 || fail_test "ns-status reported incorrect uploader battery status value."

    # If we made it here, the test passed
    echo "ns-status test passed"
}

test-autotune-core () {
    # Run autotune-core and capture output
    ../bin/oref0-autotune-core.js autotune.data.json profile.json pumpprofile.json 2>stderr_output 1>stdout_output

    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    cat stderr_output | grep -q CRTotalCarbs || fail_test "oref0-autotune-core didn't contain expected stderr output"

    # Make sure output has accurate carb ratio data
    cat stdout_output | jq .dia | grep -q 7 || fail_test "oref0-autotune-core didn't contain expected dia output"
    cat stdout_output | jq .insulinPeakTime | grep -q 85 || fail_test "oref0-autotune-core didn't contain expected insulinPeakTime output"

    # If we made it here, the test passed
    echo "oref0-autotune-core test passed"
}

test-autotune-prep () {
    # Run autotune-prep and capture output
    ../bin/oref0-autotune-prep.js autotune.treatments.json profile.json autotune.entries.json profile.json 2>stderr_output 1>stdout_output

    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $(cat stderr_output | grep mealCOB | wc -l) -eq 82 ]] || fail_test "oref0-autotune-prep didn't contain expected stderr output"

    # Make sure output has expected data
    cat stdout_output | jq ".CRData | first" | grep -q CRInitialBG || fail_test "oref0-autotune-prep didn't contain expected CR Data output"
    cat stdout_output | jq ".CSFGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep didn't contain expected CSF Glucose Data"
    cat stdout_output | jq ".ISFGlucoseData | first" | grep -q null || fail_test "oref0-autotune-prep didn't contain expected ISF Glucose Data"
    cat stdout_output | jq ".basalGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep didn't contain expected basal Glucose Data"

    # Run autotune-prep with categorize_uam_as_basal option
    ../bin/oref0-autotune-prep.js --categorize_uam_as_basal autotune.treatments.json profile.json autotune.entries.json profile.json 2>stderr_output 1>stdout_output

    # Make sure output has expected data
    cat stdout_output | jq ".CRData | first" | grep -q CRInitialBG || fail_test "oref0-autotune-prep with categorize_uam_as_basal didn't contain expected CR Data output"
    cat stdout_output | jq ".CSFGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep with categorize_uam_as_basal didn't contain expected CSF Glucose Data"
    cat stdout_output | jq ".ISFGlucoseData | first" | grep -q null || fail_test "oref0-autotune-prep with categorize_uam_as_basal didn't contain expected ISF Glucose Data"
    cat stdout_output | jq ".basalGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep with categorize_uam_as_basal didn't contain expected basal Glucose Data"

    # Run autotune-prep with tune-insulin-curve option
    ../bin/oref0-autotune-prep.js --tune-insulin-curve autotune.treatments.json profile.json autotune.entries.json profile.json 2>stderr_output 1>stdout_output

    cat stderr_output | grep SMRDeviation | grep -q RMSDeviation || fail_test "oref0-autotune-prep with tune-insulin-curve didn't contain expected insulin peak results"

    # Make sure output has expected data
    cat stdout_output | jq ".CRData | first" | grep -q CRInitialBG || fail_test "oref0-autotune-prep with tune-insulin-curve didn't contain expected CR Data output"
    cat stdout_output | jq ".CSFGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep with tune-insulin-curve didn't contain expected CSF Glucose Data"
    cat stdout_output | jq ".ISFGlucoseData | first" | grep -q null || fail_test "oref0-autotune-prep with tune-insulin-curve didn't contain expected ISF Glucose Data"
    cat stdout_output | jq ".basalGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep with tune-insulin-curve didn't contain expected basal Glucose Data"

    # Run autotune-prep with carbhistory option
    ../bin/oref0-autotune-prep.js autotune.treatments.json profile.json autotune.entries.json profile.json carbhistory.json 2>stderr_output 1>stdout_output

    # Make sure output has expected data
    cat stdout_output | jq ".CRData | first" | grep -q CRInitialBG || fail_test "oref0-autotune-prep with carbhistory didn't contain expected CR Data output"
    cat stdout_output | jq ".CSFGlucoseData | first" | grep -q null || fail_test "oref0-autotune-prep with carbhistory didn't contain expected CSF Glucose Data"
    cat stdout_output | jq ".ISFGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep with carbhistory didn't contain expected ISF Glucose Data"
    cat stdout_output | jq ".basalGlucoseData | first" | grep -q dateString || fail_test "oref0-autotune-prep with carbhistory didn't contain expected basal Glucose Data"

    # If we made it here, the test passed
    echo "oref0-autotune-prep test passed"
}

test-calculate-iob () {
    # Run calculate-iob and capture output
    ../bin/oref0-calculate-iob.js pumphistory_zoned.json profile.json clock-zoned.json  2>stderr_output 1>stdout_output

    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "oref0-calculate-iob error: \n$ERROR_LINES"

    # Make sure output has iob
    cat stdout_output | jq ". | first" | grep -q "\"iob\":" || fail_test "oref0-calculate-iob did not report an iob"

    # Make sure output has iobWithZeroTemp
    cat stdout_output | jq ". | first" | grep -q "iobWithZeroTemp" || fail_test "oref0-calculate-iob did not report an iobWithZeroTemp"

    # Run calculate-iob with autosens option and capture output
    ../bin/oref0-calculate-iob.js pumphistory_zoned.json profile.json clock-zoned.json autosens.json 2>stderr_output 1>stdout_output

    # NOTE: oref0-calculate-iob doesn't print an error if autosens file is unable to be read
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "oref0-calculate-iob error: \n$ERROR_LINES"

    # Make sure output has iob
    cat stdout_output | jq ". | first" | grep -q "\"iob\":" || fail_test "oref0-calculate-iob did not report an iob"

    # Make sure output has iobWithZeroTemp
    cat stdout_output | jq ". | first" | grep -q "iobWithZeroTemp" || fail_test "oref0-calculate-iob did not report an iobWithZeroTemp"

    # Run calculate-iob with 24 hour pumphistory option and capture output
    ../bin/oref0-calculate-iob.js pumphistory_zoned.json profile.json clock-zoned.json autosens.json pumphistory_zoned.json 2>stderr_output 1>stdout_output

    # NOTE: oref0-calculate-iob doesn't print an error if autosens or 24 hour pump history files are unable to be read
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "oref0-calculate-iob error: \n$ERROR_LINES"

    # Make sure output has iob
    cat stdout_output | jq ". | first" | grep -q "\"iob\":" || fail_test "oref0-calculate-iob did not report an iob"

    # Make sure output has iobWithZeroTemp
    cat stdout_output | jq ". | first" | grep -q "iobWithZeroTemp" || fail_test "oref0-calculate-iob did not report an iobWithZeroTemp"

    # If we made it here, the test passed
    echo "oref0-calculate-iob test passed"
}

test-detect-sensitivity () {
    # Run detect-sensitivity and capture output
    ../bin/oref0-detect-sensitivity.js glucose.json pumphistory_zoned.json insulin_sensitivities.json basal_profile.json profile.json 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected string
    ERROR_LINES=$( cat stderr_output )
    cat stderr_output | grep -q "ISF adjusted from 100 to 100" || fail_test "oref0-detect-sensitivity error: \n$ERROR_LINES"

    # Make sure output has ratio
    cat stdout_output | jq ".ratio" | grep -q "1" || fail_test "oref0-detect-sensitivity did not report correct sensitivity"

    # Run detect-sensitivity with carbhistory and capture output
    ../bin/oref0-detect-sensitivity.js glucose.json pumphistory_zoned.json insulin_sensitivities.json basal_profile.json profile.json carbhistory.json 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected string
    ERROR_LINES=$( cat stderr_output )
    cat stderr_output | grep -q "ISF adjusted from 100 to 100" || fail_test "oref0-detect-sensitivity error: \n$ERROR_LINES"

    # Make sure output has ratio
    cat stdout_output | jq ".ratio" | grep -q "1" || fail_test "oref0-detect-sensitivity did not report correct sensitivity"

    # Run oref0-detect-sensitivity with carbhistory and temptargets and capture output
    ../bin/oref0-detect-sensitivity.js glucose.json pumphistory_zoned.json insulin_sensitivities.json basal_profile.json profile.json carbhistory.json temptargets.json 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected string
    ERROR_LINES=$( cat stderr_output )
    cat stderr_output | grep -q "ISF adjusted from 100 to 100" || fail_test "oref0-detect-sensitivity error: \n$ERROR_LINES"

    # Make sure output has ratio
    cat stdout_output | jq ".ratio" | grep -q "1" || fail_test "oref0-detect-sensitivity did not report correct sensitivity"

    # If we made it here, the test passed
    echo "oref0-detect-sensitivites test passed"
}

test-determine-basal () {
    # Run determine-basal and capture output
    ../bin/oref0-determine-basal.js iob.json temp_basal.json glucose.json profile.json 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected time
    ERROR_LINES=$( cat stderr_output )
    cat stderr_output | jq .time | grep -q "2018-09-05T14:44:11.000Z" || fail_test "oref0-determine-basal error: \n$ERROR_LINES"

    # Make sure output has expected reason
    cat stdout_output | jq ".reason" | grep -q "BG data is too old" || fail_test "oref0-determine-basal did not report correct reason"

    # Run determine-basal with options
    ../bin/oref0-determine-basal.js --reservoir reservoir.json iob.json --currentTime "2018-09-05T09:44:11-05:00" temp_basal.json glucose.json --auto-sens autosens.json profile.json --meal meal.json 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected time
    ERROR_LINES=$( cat stderr_output )
    cat stderr_output | tail -n 2 | head -n 1 | jq .time | grep -q "2018-09-05T14:44:11.000Z" || fail_test "oref0-determine-basal with options error: \n$ERROR_LINES"

    # Make sure output has reason
    cat stdout_output | jq ".reason" | grep -q "BG data is too old" || fail_test "oref0-determine-basal with options did not report correct reason"

    # If we made it here, the test passed
    echo "oref0-determine-basal test passed"
}

test-find-insulin-uses () {
    # Run find-insulin-uses and capture output
    ../bin/oref0-find-insulin-uses.js pumphistory_zoned.json profile.json 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected string
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "find-insulin-uses error: \n$ERROR_LINES"

    # Make sure output has started_at
    cat stdout_output | jq ".[] | .started_at " | grep -q "2018-09-04T12:29:37.000Z" || fail_test "oref0-find-insulin-uses did not report correct started_at"

    # If we made it here, the test passed
    echo "oref0-find-insulin-uses test passed"
}

test-get-profile () {
    # Run get-profile and capture output
    ../bin/oref0-get-profile.js settings.json bg_targets.json insulin_sensitivities.json basal_profile.json 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected string
    ERROR_LINES=$( cat stderr_output )

    cat stderr_output | grep -q "No temptargets found" || fail_test "oref0-get-profile did not provide expected stderr output:\n$ERROR_LINES"

    # Make sure output has suspend_zeros_iob
    cat stdout_output | jq ".suspend_zeros_iob" | grep -q "true" || fail_test "oref0-get-profile did not report correct suspend_zeros_iob setting"

    # Run get-profile and capture output
    ../bin/oref0-get-profile.js settings.json bg_targets.json insulin_sensitivities.json basal_profile.json preferences.json carb_ratios.json temptargets.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )

    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "get-profile error: \n$ERROR_LINES"

    # Make sure output has suspend_zeros_iob
    cat stdout_output | jq ".suspend_zeros_iob" | grep -q "true" || fail_test "oref0-get-profile did not report correct suspend_zeros_iob setting"

    # Run get-profile and capture output
    ../bin/oref0-get-profile.js settings.json bg_targets.json insulin_sensitivities.json basal_profile.json preferences.json carb_ratios.json temptargets.json --model=model.json --autotune profile.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )

    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "get-profile error: \n$ERROR_LINES"

    # Make sure output has suspend_zeros_iob
    cat stdout_output | jq ".suspend_zeros_iob" | grep -q "true" || fail_test "oref0-get-profile did not report correct suspend_zeros_iob setting"

    # If we made it here, the test passed
    echo "oref0-get-profile test passed"
}

test-html () {
    # Run html and capture output
    ../bin/oref0-html.js glucose.json iob.json basal_profile.json temp_basal.json suggested.json enacted.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "html error: \n$ERROR_LINES"

    # Make sure output has expected mealCOB value
    cat stdout_output | grep -q "mealCOB: ???g" || fail_test "oref0-html did not report correct mealCOB"

    # Run html and capture output
    ../bin/oref0-html.js glucose.json iob.json basal_profile.json temp_basal.json suggested.json enacted.json meal.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )

    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "html error: \n$ERROR_LINES"

    # Make sure output has expected mealCOB value
    cat stdout_output | grep -q "mealCOB: 0g" || fail_test "oref0-html did not report correct mealCOB"

    # If we made it here, the test passed
    echo "oref0-html test passed"
}

test-meal () {
    # Run meal and capture output
    ../bin/oref0-meal.js pumphistory_zoned.json profile.json clock-zoned.json glucose.json basal_profile.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "meal error: \n$ERROR_LINES"

    # Make sure output has expected carbs value
    cat stdout_output | jq .carbs | grep -q "0" || fail_test "oref0-meal did not report correct carbs"

    # Run meal and capture output
    ../bin/oref0-meal.js pumphistory_zoned.json profile.json clock-zoned.json glucose.json basal_profile.json carbhistory.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )

    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "meal error: \n$ERROR_LINES"

    # Make sure output has expected carbs value
    cat stdout_output | jq .carbs | grep -q "0" || fail_test "oref0-meal did not report correct carbs"

    # If we made it here, the test passed
    echo "oref0-meal test passed"
}

test-normalize-temps () {
    # Run normalize-temps and capture output
    ../bin/oref0-normalize-temps.js pumphistory_zoned.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "normalize-temps error: \n$ERROR_LINES"

    # Make sure output has expected timestamp
    cat stdout_output | jq ".[] | .timestamp" | head -n 1 | grep -q "2018-09-05T10:24:59-05:00" || fail_test "oref0-normalize-temps did not report correct first timestamp"

    # If we made it here, the test passed
    echo "oref0-normalize-temps test passed"
}

test-raw () {
    # Run raw and capture output
    ../bin/oref0-raw.js raw_glucose.json cal.json 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "raw error: \n$ERROR_LINES"

    # Make sure output has expected number of glucose values
    cat stdout_output | jq ".[] | .glucose" | wc -l | grep -q "288" || fail_test "oref0-raw did not report correct number of glucose readings"

    # Run raw and capture output
    ../bin/oref0-raw.js raw_glucose.json cal.json 120 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )

    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "raw error: \n$ERROR_LINES"

    # Make sure output has expected number of glucose values above MAX_RAW
    cat stdout_output | jq ".[] | .noise" | grep "3" | wc -l | grep -q 175 || fail_test "oref0-raw did not report correct glucose readings above MAX_RAW"

    # If we made it here, the test passed
    echo "oref0-raw test passed"
}

test-set-local-temptarget () {
    # Run raw and capture output
    ../bin/oref0-set-local-temptarget.js 80 60 2>stderr_output 1>stdout_output

    # Make sure stderr output doesn't have anything
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )
    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "set-local-temptarget error: \n$ERROR_LINES"

    # Make sure output has expected targetBottom
    cat stdout_output | jq ".targetBottom" | grep -q "80" || fail_test "oref0-set-local-temptarget did not report correct targetBottom"

    # Run set-local-temptarget and capture output
    ../bin/oref0-set-local-temptarget.js 80 60 2017-10-18:00:15:00.000Z 2>stderr_output 1>stdout_output

    # Make sure stderr output contains expected string
    ERROR_LINE_COUNT=$( cat stderr_output | wc -l )
    ERROR_LINES=$( cat stderr_output )

    [[ $ERROR_LINE_COUNT = 0 ]] || fail_test "set-local-temptarget error: \n$ERROR_LINES"

    # Make sure output has ratio
    cat stdout_output | jq ".created_at" | grep -q "2017-10-18T00:15:00.000Z" || fail_test "oref0-set-local-temptarget did not report correct created_at"

    # If we made it here, the test passed
    echo "oref0-set-local-temptarget test passed"
}

generate_test_files () {

    # Make a fake preferences.json to test the commands that extract values from it
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

    # Make a dummy profile.json
    cat >profile.json <<EOT
{
   "A52_risk_enable": false,
   "allowSMB_with_high_temptarget": false,
   "autosens_max": 1.2,
   "autosens_min": 0.8,
   "autotune_isf_adjustmentFraction": 0,
   "basalprofile": [
      {
         "i": 0,
         "minutes": 0,
         "rate": 0.63,
         "start": "00:00:00"
      }
   ],
   "bg_targets": {
      "first": 0,
      "targets": [
         {
            "high": 110,
            "i": 0,
            "low": 110,
            "max_bg": 110,
            "min_bg": 110,
            "offset": 0,
            "start": "00:00:00",
            "x": 0
         }
      ],
      "units": "mg/dL",
      "user_preferred_units": "mg/dL"
   },
   "bolussnooze_dia_divisor": 2,
   "carb_ratio": 22.142,
   "carb_ratios": {
      "first": 1,
      "schedule": [
         {
            "i": 0,
            "offset": 0,
            "ratio": 20,
            "start": "00:00:00",
            "x": 0
         }
      ],
      "units": "grams"
   },
   "carbsReqThreshold": 1,
   "csf": 3.815,
   "current_basal": 0.65,
   "current_basal_safety_multiplier": 4,
   "curve": "rapid-acting",
   "dia": 7,
   "enableSMB_after_carbs": false,
   "enableSMB_always": true,
   "enableSMB_with_COB": true,
   "enableSMB_with_temptarget": true,
   "enableUAM": true,
   "exercise_mode": false,
   "half_basal_exercise_target": 160,
   "high_temptarget_raises_sensitivity": false,
   "insulinPeakTime": 85,
   "isfProfile": {
      "first": 1,
      "sensitivities": [
         {
            "endOffset": 1440,
            "i": 0,
            "offset": 0,
            "sensitivity": 100,
            "start": "00:00:00",
            "x": 0
         }
      ],
      "units": "mg/dL",
      "user_preferred_units": "mg/dL"
   },
   "low_temptarget_lowers_sensitivity": false,
   "maxCOB": 120,
   "maxSMBBasalMinutes": 30,
   "max_basal": 2.8,
   "max_bg": 110,
   "max_daily_basal": 0.75,
   "max_daily_safety_multiplier": 3,
   "max_iob": 7,
   "min_5m_carbimpact": 8,
   "min_bg": 110,
   "model": "723",
   "offline_hotspot": false,
   "out_units": "mg/dL",
   "remainingCarbsCap": 90,
   "remainingCarbsFraction": 1,
   "resistance_lowers_target": false,
   "rewind_resets_autosens": true,
   "sens": 100,
   "sensitivity_raises_target": true,
   "suspend_zeros_iob": true,
   "unsuspend_if_no_temp": false,
   "useCustomPeakTime": true
}
EOT

    # Make a dummy pumpprofile.json
    cat >pumpprofile.json <<EOT
{
   "A52_risk_enable": false,
   "allowSMB_with_high_temptarget": false,
   "autosens_max": 1.2,
   "autosens_min": 0.8,
   "autotune_isf_adjustmentFraction": 0,
   "basalprofile": [
      {
         "i": 0,
         "minutes": 0,
         "rate": 0.63,
         "start": "00:00:00"
      }
   ],
   "bg_targets": {
      "first": 0,
      "targets": [
         {
            "high": 110,
            "i": 0,
            "low": 110,
            "max_bg": 110,
            "min_bg": 110,
            "offset": 0,
            "start": "00:00:00",
            "x": 0
         }
      ],
      "units": "mg/dL",
      "user_preferred_units": "mg/dL"
   },
   "bolussnooze_dia_divisor": 2,
   "carb_ratio": 22.142,
   "carb_ratios": {
      "first": 1,
      "schedule": [
         {
            "i": 0,
            "offset": 0,
            "ratio": 20,
            "start": "00:00:00",
            "x": 0
         }
      ],
      "units": "grams"
   },
   "carbsReqThreshold": 1,
   "csf": 3.815,
   "current_basal": 0.65,
   "current_basal_safety_multiplier": 4,
   "curve": "rapid-acting",
   "dia": 8,
   "enableSMB_after_carbs": false,
   "enableSMB_always": true,
   "enableSMB_with_COB": true,
   "enableSMB_with_temptarget": true,
   "enableUAM": true,
   "exercise_mode": false,
   "half_basal_exercise_target": 160,
   "high_temptarget_raises_sensitivity": false,
   "insulinPeakTime": 90,
   "isfProfile": {
      "first": 1,
      "sensitivities": [
         {
            "endOffset": 1440,
            "i": 0,
            "offset": 0,
            "sensitivity": 100,
            "start": "00:00:00",
            "x": 0
         }
      ],
      "units": "mg/dL",
      "user_preferred_units": "mg/dL"
   },
   "low_temptarget_lowers_sensitivity": false,
   "maxCOB": 120,
   "maxSMBBasalMinutes": 30,
   "max_basal": 2.8,
   "max_bg": 110,
   "max_daily_basal": 0.75,
   "max_daily_safety_multiplier": 3,
   "max_iob": 7,
   "min_5m_carbimpact": 8,
   "min_bg": 110,
   "model": "723",
   "offline_hotspot": false,
   "out_units": "mg/dL",
   "remainingCarbsCap": 90,
   "remainingCarbsFraction": 1,
   "resistance_lowers_target": false,
   "rewind_resets_autosens": true,
   "sens": 100,
   "sensitivity_raises_target": true,
   "suspend_zeros_iob": true,
   "unsuspend_if_no_temp": false,
   "useCustomPeakTime": true
}
EOT

    # Make a dummy basal_profile.json
    cat >basal_profile.json <<EOT
[
  {
    "i": 0,
    "start": "00:00:00",
    "minutes": 0,
    "rate": 0.5
  },
  {
    "i": 1,
    "start": "05:00:00",
    "minutes": 300,
    "rate": 1.1
  }
]
EOT

    # Make a fake autosens.json
    cat >autosens.json <<EOT
{ "ratio": 0.8 }
EOT

    # Make a fake clock-zoned.json to test the commands that extract values from it
    cat >clock-zoned.json <<EOT
"2018-09-05T09:44:11-05:00"
EOT

    # Make a fake uploader.json to test the commands that extract values from it
    cat >uploader.json <<EOT
50
EOT

    # Make a fake iob.json to test the commands that extract values from it
    cat >iob.json <<EOT
[
  {
    "iob": -0.154,
    "activity": -0.0007,
    "basaliob": -0.259,
    "bolusiob": 0.105,
    "netbasalinsulin": -1.4,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T14:44:11.000Z",
    "iobWithZeroTemp": { "iob": -0.154, "activity": -0.0007, "basaliob": -0.259, "bolusiob": 0.105, "netbasalinsulin": -1.4, "bolusinsulin": 0.4, "time": "2018-09-05T14:44:11.000Z" },
    "lastBolusTime": 1536152102000,
    "lastTemp": {
      "rate": 1.05,
      "timestamp": "2018-09-05T09:39:39-05:00",
      "started_at": "2018-09-05T14:39:39.000Z",
      "date": 1536158379000,
      "duration": 5.53
    }
  },
  {
    "iob": -0.15,
    "activity": -0.0007,
    "basaliob": -0.25,
    "bolusiob": 0.099,
    "netbasalinsulin": -1.4,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T14:49:11.000Z",
    "iobWithZeroTemp": { "iob": -0.25, "activity": -0.0008, "basaliob": -0.35, "bolusiob": 0.099, "netbasalinsulin": -1.5, "bolusinsulin": 0.4, "time": "2018-09-05T14:49:11.000Z" }
  },
  {
    "iob": -0.146,
    "activity": -0.0008,
    "basaliob": -0.24,
    "bolusiob": 0.094,
    "netbasalinsulin": -1.35,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T14:54:11.000Z",
    "iobWithZeroTemp": { "iob": -0.296, "activity": -0.0009, "basaliob": -0.39, "bolusiob": 0.094, "netbasalinsulin": -1.5, "bolusinsulin": 0.4, "time": "2018-09-05T14:54:11.000Z" }
  },
  {
    "iob": -0.143,
    "activity": -0.0008,
    "basaliob": -0.231,
    "bolusiob": 0.089,
    "netbasalinsulin": -1.3,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T14:59:11.000Z",
    "iobWithZeroTemp": { "iob": -0.341, "activity": -0.001, "basaliob": -0.43, "bolusiob": 0.089, "netbasalinsulin": -1.5, "bolusinsulin": 0.4, "time": "2018-09-05T14:59:11.000Z" }
  },
  {
    "iob": -0.139,
    "activity": -0.0008,
    "basaliob": -0.222,
    "bolusiob": 0.084,
    "netbasalinsulin": -1.25,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:04:11.000Z",
    "iobWithZeroTemp": { "iob": -0.436, "activity": -0.0012, "basaliob": -0.52, "bolusiob": 0.084, "netbasalinsulin": -1.55, "bolusinsulin": 0.4, "time": "2018-09-05T15:04:11.000Z" }
  },
  {
    "iob": -0.135,
    "activity": -0.0008,
    "basaliob": -0.214,
    "bolusiob": 0.079,
    "netbasalinsulin": -1.25,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:09:11.000Z",
    "iobWithZeroTemp": { "iob": -0.579, "activity": -0.0014, "basaliob": -0.658, "bolusiob": 0.079, "netbasalinsulin": -1.7, "bolusinsulin": 0.4, "time": "2018-09-05T15:09:11.000Z" }
  },
  {
    "iob": -0.131,
    "activity": -0.0008,
    "basaliob": -0.205,
    "bolusiob": 0.074,
    "netbasalinsulin": -1.15,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:14:11.000Z",
    "iobWithZeroTemp": { "iob": -0.671, "activity": -0.0017, "basaliob": -0.746, "bolusiob": 0.074, "netbasalinsulin": -1.7, "bolusinsulin": 0.4, "time": "2018-09-05T15:14:11.000Z" }
  },
  {
    "iob": -0.126,
    "activity": -0.0008,
    "basaliob": -0.196,
    "bolusiob": 0.07,
    "netbasalinsulin": -1.15,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:19:11.000Z",
    "iobWithZeroTemp": { "iob": -0.762, "activity": -0.0021, "basaliob": -0.832, "bolusiob": 0.07, "netbasalinsulin": -1.8, "bolusinsulin": 0.4, "time": "2018-09-05T15:19:11.000Z" }
  },
  {
    "iob": -0.122,
    "activity": -0.0008,
    "basaliob": -0.188,
    "bolusiob": 0.066,
    "netbasalinsulin": -1.1,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:24:11.000Z",
    "iobWithZeroTemp": { "iob": -0.85, "activity": -0.0025, "basaliob": -0.916, "bolusiob": 0.066, "netbasalinsulin": -1.85, "bolusinsulin": 0.4, "time": "2018-09-05T15:24:11.000Z" }
  },
  {
    "iob": -0.118,
    "activity": -0.0008,
    "basaliob": -0.18,
    "bolusiob": 0.061,
    "netbasalinsulin": -1.1,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:29:11.000Z",
    "iobWithZeroTemp": { "iob": -0.987, "activity": -0.0029, "basaliob": -1.049, "bolusiob": 0.061, "netbasalinsulin": -2, "bolusinsulin": 0.4, "time": "2018-09-05T15:29:11.000Z" }
  },
  {
    "iob": -0.114,
    "activity": -0.0008,
    "basaliob": -0.172,
    "bolusiob": 0.058,
    "netbasalinsulin": -1.05,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:34:11.000Z",
    "iobWithZeroTemp": { "iob": -1.072, "activity": -0.0033, "basaliob": -1.129, "bolusiob": 0.058, "netbasalinsulin": -2.05, "bolusinsulin": 0.4, "time": "2018-09-05T15:34:11.000Z" }
  },
  {
    "iob": -0.11,
    "activity": -0.0008,
    "basaliob": -0.164,
    "bolusiob": 0.054,
    "netbasalinsulin": -1,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:39:11.000Z",
    "iobWithZeroTemp": { "iob": -1.154, "activity": -0.0038, "basaliob": -1.208, "bolusiob": 0.054, "netbasalinsulin": -2.1, "bolusinsulin": 0.4, "time": "2018-09-05T15:39:11.000Z" }
  },
  {
    "iob": -0.106,
    "activity": -0.0008,
    "basaliob": -0.157,
    "bolusiob": 0.05,
    "netbasalinsulin": -1,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:44:11.000Z",
    "iobWithZeroTemp": { "iob": -1.234, "activity": -0.0042, "basaliob": -1.284, "bolusiob": 0.05, "netbasalinsulin": -2.2, "bolusinsulin": 0.4, "time": "2018-09-05T15:44:11.000Z" }
  },
  {
    "iob": -0.102,
    "activity": -0.0008,
    "basaliob": -0.149,
    "bolusiob": 0.047,
    "netbasalinsulin": -0.95,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:49:11.000Z",
    "iobWithZeroTemp": { "iob": -1.311, "activity": -0.0047, "basaliob": -1.358, "bolusiob": 0.047, "netbasalinsulin": -2.25, "bolusinsulin": 0.4, "time": "2018-09-05T15:49:11.000Z" }
  },
  {
    "iob": -0.099,
    "activity": -0.0008,
    "basaliob": -0.142,
    "bolusiob": 0.044,
    "netbasalinsulin": -0.9,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:54:11.000Z",
    "iobWithZeroTemp": { "iob": -1.436, "activity": -0.0053, "basaliob": -1.48, "bolusiob": 0.044, "netbasalinsulin": -2.35, "bolusinsulin": 0.4, "time": "2018-09-05T15:54:11.000Z" }
  },
  {
    "iob": -0.095,
    "activity": -0.0008,
    "basaliob": -0.135,
    "bolusiob": 0.041,
    "netbasalinsulin": -0.85,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T15:59:11.000Z",
    "iobWithZeroTemp": { "iob": -1.509, "activity": -0.0058, "basaliob": -1.549, "bolusiob": 0.041, "netbasalinsulin": -2.4, "bolusinsulin": 0.4, "time": "2018-09-05T15:59:11.000Z" }
  },
  {
    "iob": -0.091,
    "activity": -0.0007,
    "basaliob": -0.129,
    "bolusiob": 0.038,
    "netbasalinsulin": -0.8,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:04:11.000Z",
    "iobWithZeroTemp": { "iob": -1.579, "activity": -0.0063, "basaliob": -1.616, "bolusiob": 0.038, "netbasalinsulin": -2.45, "bolusinsulin": 0.4, "time": "2018-09-05T16:04:11.000Z" }
  },
  {
    "iob": -0.087,
    "activity": -0.0007,
    "basaliob": -0.122,
    "bolusiob": 0.035,
    "netbasalinsulin": -0.75,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:09:11.000Z",
    "iobWithZeroTemp": { "iob": -1.696, "activity": -0.0069, "basaliob": -1.73, "bolusiob": 0.035, "netbasalinsulin": -2.55, "bolusinsulin": 0.4, "time": "2018-09-05T16:09:11.000Z" }
  },
  {
    "iob": -0.084,
    "activity": -0.0007,
    "basaliob": -0.116,
    "bolusiob": 0.032,
    "netbasalinsulin": -0.75,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:14:11.000Z",
    "iobWithZeroTemp": { "iob": -1.76, "activity": -0.0074, "basaliob": -1.792, "bolusiob": 0.032, "netbasalinsulin": -2.65, "bolusinsulin": 0.4, "time": "2018-09-05T16:14:11.000Z" }
  },
  {
    "iob": -0.08,
    "activity": -0.0007,
    "basaliob": -0.11,
    "bolusiob": 0.03,
    "netbasalinsulin": -0.75,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:19:11.000Z",
    "iobWithZeroTemp": { "iob": -1.821, "activity": -0.008, "basaliob": -1.851, "bolusiob": 0.03, "netbasalinsulin": -2.75, "bolusinsulin": 0.4, "time": "2018-09-05T16:19:11.000Z" }
  },
  {
    "iob": -0.077,
    "activity": -0.0007,
    "basaliob": -0.104,
    "bolusiob": 0.028,
    "netbasalinsulin": -0.7,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:24:11.000Z",
    "iobWithZeroTemp": { "iob": -1.88, "activity": -0.0085, "basaliob": -1.908, "bolusiob": 0.028, "netbasalinsulin": -2.8, "bolusinsulin": 0.4, "time": "2018-09-05T16:24:11.000Z" }
  },
  {
    "iob": -0.073,
    "activity": -0.0007,
    "basaliob": -0.099,
    "bolusiob": 0.025,
    "netbasalinsulin": -0.65,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:29:11.000Z",
    "iobWithZeroTemp": { "iob": -1.986, "activity": -0.009, "basaliob": -2.012, "bolusiob": 0.025, "netbasalinsulin": -2.9, "bolusinsulin": 0.4, "time": "2018-09-05T16:29:11.000Z" }
  },
  {
    "iob": -0.07,
    "activity": -0.0006,
    "basaliob": -0.094,
    "bolusiob": 0.023,
    "netbasalinsulin": -0.65,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:34:11.000Z",
    "iobWithZeroTemp": {
      "iob": -2.04, "activity": -0.0096, "basaliob": -2.063, "bolusiob": 0.023, "netbasalinsulin": -3, "bolusinsulin": 0.4, "time": "2018-09-05T16:34:11.000Z" } },
  {
    "iob": -0.067,
    "activity": -0.0006,
    "basaliob": -0.088,
    "bolusiob": 0.021,
    "netbasalinsulin": -0.6,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:39:11.000Z",
    "iobWithZeroTemp": { "iob": -2.091, "activity": -0.0101, "basaliob": -2.112, "bolusiob": 0.021, "netbasalinsulin": -3.05, "bolusinsulin": 0.4, "time": "2018-09-05T16:39:11.000Z" }
  },
  {
    "iob": -0.064,
    "activity": -0.0006,
    "basaliob": -0.084,
    "bolusiob": 0.02,
    "netbasalinsulin": -0.55,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:44:11.000Z",
    "iobWithZeroTemp": { "iob": -2.139, "activity": -0.0106, "basaliob": -2.158, "bolusiob": 0.02, "netbasalinsulin": -3.1, "bolusinsulin": 0.4, "time": "2018-09-05T16:44:11.000Z" }
  },
  {
    "iob": -0.061,
    "activity": -0.0006,
    "basaliob": -0.079,
    "bolusiob": 0.018,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:49:11.000Z",
    "iobWithZeroTemp": { "iob": -2.184, "activity": -0.0111, "basaliob": -2.202, "bolusiob": 0.018, "netbasalinsulin": -3.15, "bolusinsulin": 0.4, "time": "2018-09-05T16:49:11.000Z" }
  },
  {
    "iob": -0.058,
    "activity": -0.0006,
    "basaliob": -0.074,
    "bolusiob": 0.016,
    "netbasalinsulin": -0.45,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:54:11.000Z",
    "iobWithZeroTemp": { "iob": -2.278, "activity": -0.0116, "basaliob": -2.294, "bolusiob": 0.016, "netbasalinsulin": -3.25, "bolusinsulin": 0.4, "time": "2018-09-05T16:54:11.000Z" }
  },
  {
    "iob": -0.055,
    "activity": -0.0006,
    "basaliob": -0.07,
    "bolusiob": 0.015,
    "netbasalinsulin": -0.45,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T16:59:11.000Z",
    "iobWithZeroTemp": { "iob": -2.318, "activity": -0.0121, "basaliob": -2.333, "bolusiob": 0.015, "netbasalinsulin": -3.35, "bolusinsulin": 0.4, "time": "2018-09-05T16:59:11.000Z" }
  },
  {
    "iob": -0.052,
    "activity": -0.0005,
    "basaliob": -0.066,
    "bolusiob": 0.013,
    "netbasalinsulin": -0.4,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:04:11.000Z",
    "iobWithZeroTemp": { "iob": -2.357, "activity": -0.0126, "basaliob": -2.37, "bolusiob": 0.013, "netbasalinsulin": -3.4, "bolusinsulin": 0.4, "time": "2018-09-05T17:04:11.000Z" }
  },
  {
    "iob": -0.05,
    "activity": -0.0005,
    "basaliob": -0.062,
    "bolusiob": 0.012,
    "netbasalinsulin": -0.35,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:09:11.000Z",
    "iobWithZeroTemp": { "iob": -2.392, "activity": -0.0131, "basaliob": -2.405, "bolusiob": 0.012, "netbasalinsulin": -3.45, "bolusinsulin": 0.4, "time": "2018-09-05T17:09:11.000Z" }
  },
  {
    "iob": -0.047,
    "activity": -0.0005,
    "basaliob": -0.058,
    "bolusiob": 0.011,
    "netbasalinsulin": -0.3,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:14:11.000Z",
    "iobWithZeroTemp": { "iob": -2.426, "activity": -0.0135, "basaliob": -2.437, "bolusiob": 0.011, "netbasalinsulin": -3.5, "bolusinsulin": 0.4, "time": "2018-09-05T17:14:11.000Z" }
  },
  {
    "iob": -0.044,
    "activity": -0.0005,
    "basaliob": -0.054,
    "bolusiob": 0.01,
    "netbasalinsulin": -0.25,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:19:11.000Z",
    "iobWithZeroTemp": { "iob": -2.457, "activity": -0.0139, "basaliob": -2.467, "bolusiob": 0.01, "netbasalinsulin": -3.55, "bolusinsulin": 0.4, "time": "2018-09-05T17:19:11.000Z" }
  },
  {
    "iob": -0.042,
    "activity": -0.0005,
    "basaliob": -0.051,
    "bolusiob": 0.009,
    "netbasalinsulin": -0.2,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:24:11.000Z",
    "iobWithZeroTemp": { "iob": -2.487, "activity": -0.0143, "basaliob": -2.496, "bolusiob": 0.009, "netbasalinsulin": -3.6, "bolusinsulin": 0.4, "time": "2018-09-05T17:24:11.000Z" }
  },
  {
    "iob": -0.04,
    "activity": -0.0005,
    "basaliob": -0.048,
    "bolusiob": 0.008,
    "netbasalinsulin": -0.2,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:29:11.000Z",
    "iobWithZeroTemp": { "iob": -2.564, "activity": -0.0147, "basaliob": -2.572, "bolusiob": 0.008, "netbasalinsulin": -3.75, "bolusinsulin": 0.4, "time": "2018-09-05T17:29:11.000Z" }
  },
  {
    "iob": -0.037,
    "activity": -0.0005,
    "basaliob": -0.044,
    "bolusiob": 0.007,
    "netbasalinsulin": -0.2,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:34:11.000Z",
    "iobWithZeroTemp": { "iob": -2.59, "activity": -0.0151, "basaliob": -2.597, "bolusiob": 0.007, "netbasalinsulin": -3.85, "bolusinsulin": 0.4, "time": "2018-09-05T17:34:11.000Z" }
  },
  {
    "iob": -0.035,
    "activity": -0.0005,
    "basaliob": -0.041,
    "bolusiob": 0.007,
    "netbasalinsulin": -0.25,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:39:11.000Z",
    "iobWithZeroTemp": { "iob": -2.613, "activity": -0.0155, "basaliob": -2.62, "bolusiob": 0.007, "netbasalinsulin": -4, "bolusinsulin": 0.4, "time": "2018-09-05T17:39:11.000Z" }
  },
  {
    "iob": -0.033,
    "activity": -0.0004,
    "basaliob": -0.038,
    "bolusiob": 0.006,
    "netbasalinsulin": -0.25,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:44:11.000Z",
    "iobWithZeroTemp": { "iob": -2.635, "activity": -0.0158, "basaliob": -2.641, "bolusiob": 0.006, "netbasalinsulin": -4.1, "bolusinsulin": 0.4, "time": "2018-09-05T17:44:11.000Z" }
  },
  {
    "iob": -0.03,
    "activity": -0.0004,
    "basaliob": -0.036,
    "bolusiob": 0.005,
    "netbasalinsulin": -0.3,
    "bolusinsulin": 0.4,
    "time": "2018-09-05T17:49:11.000Z",
    "iobWithZeroTemp": { "iob": -2.655, "activity": -0.0162, "basaliob": -2.66, "bolusiob": 0.005, "netbasalinsulin": -4.25, "bolusinsulin": 0.4, "time": "2018-09-05T17:49:11.000Z" }
  },
  {
    "iob": -0.028,
    "activity": -0.0004,
    "basaliob": -0.033,
    "bolusiob": 0.005,
    "netbasalinsulin": -0.3,
    "bolusinsulin": 0.2,
    "time": "2018-09-05T17:54:11.000Z",
    "iobWithZeroTemp": { "iob": -2.673, "activity": -0.0165, "basaliob": -2.678, "bolusiob": 0.005, "netbasalinsulin": -4.35, "bolusinsulin": 0.2, "time": "2018-09-05T17:54:11.000Z" }
  },
  {
    "iob": -0.026,
    "activity": -0.0004,
    "basaliob": -0.031,
    "bolusiob": 0.004,
    "netbasalinsulin": -0.35,
    "bolusinsulin": 0.2,
    "time": "2018-09-05T17:59:11.000Z",
    "iobWithZeroTemp": { "iob": -2.69, "activity": -0.0168, "basaliob": -2.694, "bolusiob": 0.004, "netbasalinsulin": -4.5, "bolusinsulin": 0.2, "time": "2018-09-05T17:59:11.000Z" }
  },
  {
    "iob": -0.024,
    "activity": -0.0004,
    "basaliob": -0.028,
    "bolusiob": 0.004,
    "netbasalinsulin": -0.4,
    "bolusinsulin": 0.2,
    "time": "2018-09-05T18:04:11.000Z",
    "iobWithZeroTemp": { "iob": -2.705, "activity": -0.0171, "basaliob": -2.709, "bolusiob": 0.004, "netbasalinsulin": -4.65, "bolusinsulin": 0.2, "time": "2018-09-05T18:04:11.000Z" }
  },
  {
    "iob": -0.023,
    "activity": -0.0004,
    "basaliob": -0.026,
    "bolusiob": 0.003,
    "netbasalinsulin": -0.45,
    "bolusinsulin": 0.1,
    "time": "2018-09-05T18:09:11.000Z",
    "iobWithZeroTemp": { "iob": -2.719, "activity": -0.0173, "basaliob": -2.723, "bolusiob": 0.003, "netbasalinsulin": -4.8, "bolusinsulin": 0.1, "time": "2018-09-05T18:09:11.000Z" }
  },
  {
    "iob": -0.021,
    "activity": -0.0003,
    "basaliob": -0.024,
    "bolusiob": 0.003,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.1,
    "time": "2018-09-05T18:14:11.000Z",
    "iobWithZeroTemp": { "iob": -2.732, "activity": -0.0176, "basaliob": -2.735, "bolusiob": 0.003, "netbasalinsulin": -4.95, "bolusinsulin": 0.1, "time": "2018-09-05T18:14:11.000Z" }
  },
  {
    "iob": -0.019,
    "activity": -0.0003,
    "basaliob": -0.022,
    "bolusiob": 0.003,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.1,
    "time": "2018-09-05T18:19:11.000Z",
    "iobWithZeroTemp": { "iob": -2.644, "activity": -0.0178, "basaliob": -2.646, "bolusiob": 0.003, "netbasalinsulin": -4.95, "bolusinsulin": 0.1, "time": "2018-09-05T18:19:11.000Z" }
  },
  {
    "iob": -0.018,
    "activity": -0.0003,
    "basaliob": -0.02,
    "bolusiob": 0.002,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.1,
    "time": "2018-09-05T18:24:11.000Z",
    "iobWithZeroTemp": { "iob": -2.554, "activity": -0.0179, "basaliob": -2.557, "bolusiob": 0.002, "netbasalinsulin": -4.95, "bolusinsulin": 0.1, "time": "2018-09-05T18:24:11.000Z" }
  },
  {
    "iob": -0.016,
    "activity": -0.0003,
    "basaliob": -0.018,
    "bolusiob": 0.002,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.1,
    "time": "2018-09-05T18:29:11.000Z",
    "iobWithZeroTemp": { "iob": -2.465, "activity": -0.0179, "basaliob": -2.467, "bolusiob": 0.002, "netbasalinsulin": -4.95, "bolusinsulin": 0.1, "time": "2018-09-05T18:29:11.000Z" }
  },
  {
    "iob": -0.015,
    "activity": -0.0003,
    "basaliob": -0.017,
    "bolusiob": 0.002,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.1,
    "time": "2018-09-05T18:34:11.000Z",
    "iobWithZeroTemp": { "iob": -2.376, "activity": -0.0179, "basaliob": -2.377, "bolusiob": 0.002, "netbasalinsulin": -4.95, "bolusinsulin": 0.1, "time": "2018-09-05T18:34:11.000Z" }
  },
  {
    "iob": -0.014,
    "activity": -0.0002,
    "basaliob": -0.015,
    "bolusiob": 0.002,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.1,
    "time": "2018-09-05T18:39:11.000Z",
    "iobWithZeroTemp": { "iob": -2.287, "activity": -0.0178, "basaliob": -2.288, "bolusiob": 0.002, "netbasalinsulin": -4.95, "bolusinsulin": 0.1, "time": "2018-09-05T18:39:11.000Z" }
  }
]
EOT

    # Make a fake suggested.json to test the commands that extract values from it
    cat >suggested.json <<EOT
{
  "temp": "absolute",
  "bg": 124,
  "tick": "+15",
  "eventualBG": 202,
  "insulinReq": 0.56,
  "reservoir": "51.25\n",
  "deliverAt": "2018-09-05T14:52:02.138Z",
  "sensitivityRatio": 0.88,
  "predBGs": {
    "IOB": [
      124, 136, 146, 156, 164, 170, 176, 180, 183, 185, 186, 185, 184, 182, 180, 179,
      177, 175, 174, 172, 170, 169, 167, 165, 164, 162, 160, 159, 157, 156, 154, 153,
      152, 150, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 139, 138, 137
    ],
    "ZT": [
      124, 124, 124, 124, 123, 123, 122, 122, 121, 121, 121, 121, 121, 122, 122
    ],
    "UAM": [
      124, 138, 151, 164, 175, 185, 194, 203, 210, 217, 223, 227, 231, 235, 237, 239,
      239, 239, 239, 237, 235, 234, 232, 230, 229, 227, 225, 224, 222, 221, 220, 218,
      217, 216, 214, 213, 212, 211, 210, 209, 208, 207, 206, 205, 204, 203, 203, 202
    ]
  },
  "COB": 0,
  "IOB": 0.599,
  "reason": "COB: 0, Dev: 89, BGI: 0, ISF: 114, CR: 22.14, Target: 105, minPredBG 169, minGuardBG 138, IOBpredBG 137, UAMpredBG 202; Eventual BG 202 >= 105,  insulinReq 0.56; setting 30m low temp of 0.13U/h. Microbolusing 0.2U. ",
  "units": 0.2,
  "rate": 0.13,
  "duration": 30
}
EOT

    # Make a fake enacted.json to test the commands that extract values from it
    cat >enacted.json <<EOT
{
  "temp": "absolute",
  "bg": 124,
  "tick": "+15",
  "eventualBG": 202,
  "insulinReq": 0.56,
  "reservoir": "51.25\n",
  "deliverAt": "2018-09-05T14:52:02.138Z",
  "sensitivityRatio": 0.88,
  "predBGs": {
    "IOB": [
      124, 136, 146, 156, 164, 170, 176, 180, 183, 185, 186, 185, 184, 182, 180, 179,
      177, 175, 174, 172, 170, 169, 167, 165, 164, 162, 160, 159, 157, 156, 154, 153,
      152, 150, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 139, 138, 137
    ],
    "ZT": [
      124, 124, 124, 124, 123, 123, 122, 122, 121, 121, 121, 121, 121, 122, 122
    ],
    "UAM": [
      124, 138, 151, 164, 175, 185, 194, 203, 210, 217, 223, 227, 231, 235, 237, 239,
      239, 239, 239, 237, 235, 234, 232, 230, 229, 227, 225, 224, 222, 221, 220, 218,
      217, 216, 214, 213, 212, 211, 210, 209, 208, 207, 206, 205, 204, 203, 203, 202
    ]
  },
  "COB": 0,
  "IOB": 0.599,
  "reason": "COB: 0, Dev: 89, BGI: 0, ISF: 114, CR: 22.14, Target: 105, minPredBG 169, minGuardBG 138, IOBpredBG 137, UAMpredBG 202; Eventual BG 202 >= 105,  insulinReq 0.56; setting 30m low temp of 0.13U/h. Microbolusing 0.2U. ",
  "units": 0.2,
  "rate": 0.13,
  "duration": 30
}
EOT

    # Make a fake battery.json to test the commands that extract values from it
    cat >battery.json <<EOT
{
  "voltage": 1.56,
  "string": "normal"
}
EOT

    # Make a fake reservoir.json to test the commands that extract values from it
    cat >reservoir.json <<EOT
51.05
EOT

    # Make a fake status.json to test the commands that extract values from it
    cat >status.json <<EOT
{
  "status": "normal",
  "bolusing": true,
  "suspended": false
}
EOT

    # Make a fake cal.json to test the commands that extract values from it
    cat >cal.json <<EOT
[ {"date":1535947102261,"scale":1,"intercept":34058.44519508067,"slope":955.9093730012227,"type":"LeastSquaresRegression"} ]
EOT

    # Make a fake carbhistory.json to test the commands that extract values from it
   cat >carbhistory.json <<EOT
[
  {
    "_id": "5b8f4438c09b910004e36513",
    "created_at": "2018-09-05T02:00:00Z",
    "eventType": "Meal Bolus",
    "glucose": 108,
    "glucoseType": "Finger",
    "carbs": 62,
    "units": "mg/dl",
    "enteredBy": "User",
    "NSCLIENT_ID": 1536115767681,
    "insulin": null
  },
  {
    "_id": "5b8f227fc09b910004e36491",
    "created_at": "2018-09-05T00:25:27Z",
    "eventType": "Carb Correction",
    "glucose": 47,
    "glucoseType": "Sensor",
    "carbs": 30,
    "units": "mg/dl",
    "NSCLIENT_ID": 1536107135539,
    "insulin": null
  }
]
EOT

    # Make a fake edison-battery.json to test the commands that extract values from it
    cat >edison-battery.json <<EOT
{"batteryVoltage":4064, "battery":88}
EOT

    # Make a fake glucose.json to test the commands that extract values from it
    cat >glucose.json <<EOT
[
  {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T14:58:09.623Z", "sgv": 142,
    "device": "xdripjs://RigName", "filtered": 168800, "date": 1536159489623, "unfiltered": 184416,
    "rssi": -82, "type": "sgv", "glucose": 142
  }, {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T14:53:09.786Z", "sgv": 136,
    "device": "xdripjs://RigName", "filtered": 153632, "date": 1536159189786, "unfiltered": 178496,
    "rssi": -79, "type": "sgv", "glucose": 136
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T14:48:09.731Z", "sgv": 124,
    "device": "xdripjs://RigName", "filtered": 141120, "date": 1536158889731, "unfiltered": 165536,
    "rssi": -63, "type": "sgv", "glucose": 124
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T14:43:09.747Z", "sgv": 109,
    "device": "xdripjs://RigName", "filtered": 134432, "date": 1536158589747, "unfiltered": 150048,
    "rssi": -67, "type": "sgv", "glucose": 109
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:38:10.581Z", "sgv": 93,
    "device": "xdripjs://RigName", "filtered": 133056, "date": 1536158290581, "unfiltered": 133728,
    "rssi": -60, "type": "sgv", "glucose": 93
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:23:09.777Z", "sgv": 94,
    "device": "xdripjs://RigName", "filtered": 138176, "date": 1536157389777, "unfiltered": 134592,
    "rssi": -76, "type": "sgv", "glucose": 94
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:18:09.822Z", "sgv": 97,
    "device": "xdripjs://RigName", "filtered": 140128, "date": 1536157089822, "unfiltered": 137376,
    "rssi": -77, "type": "sgv", "glucose": 97
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:13:09.824Z", "sgv": 99,
    "device": "xdripjs://RigName", "filtered": 141888, "date": 1536156789824, "unfiltered": 139520,
    "rssi": -72, "type": "sgv", "glucose": 99
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:08:09.829Z", "sgv": 100,
    "device": "xdripjs://RigName", "filtered": 143488, "date": 1536156489829, "unfiltered": 140416,
    "rssi": -68, "type": "sgv", "glucose": 100
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:03:09.858Z", "sgv": 102,
    "device": "xdripjs://RigName", "filtered": 144864, "date": 1536156189858, "unfiltered": 142784,
    "rssi": -72, "type": "sgv", "glucose": 102
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:58:10.019Z", "sgv": 104,
    "device": "xdripjs://RigName", "filtered": 146208, "date": 1536155890019, "unfiltered": 144416,
    "rssi": -77, "type": "sgv", "glucose": 104
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:53:10.088Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 147648, "date": 1536155590088, "unfiltered": 145984,
    "rssi": -72, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:48:09.748Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 149248, "date": 1536155289748, "unfiltered": 146144,
    "rssi": -75, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:43:10.020Z", "sgv": 108,
    "device": "xdripjs://RigName", "filtered": 150752, "date": 1536154990020, "unfiltered": 149024,
    "rssi": -63, "type": "sgv", "glucose": 108
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:38:10.121Z", "sgv": 108,
    "device": "xdripjs://RigName", "filtered": 151808, "date": 1536154690121, "unfiltered": 149440,
    "rssi": -65, "type": "sgv", "glucose": 108
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:28:10.277Z", "sgv": 111,
    "device": "xdripjs://RigName", "filtered": 152000, "date": 1536154090277, "unfiltered": 151808,
    "rssi": -60, "type": "sgv", "glucose": 111
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:23:10.502Z", "sgv": 112,
    "device": "xdripjs://RigName", "filtered": 151232, "date": 1536153790502, "unfiltered": 152832,
    "rssi": -80, "type": "sgv", "glucose": 112
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:18:09.814Z", "sgv": 111,
    "device": "xdripjs://RigName", "filtered": 149824, "date": 1536153489814, "unfiltered": 151776,
    "rssi": -67, "type": "sgv", "glucose": 111
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:13:09.799Z", "sgv": 109,
    "device": "xdripjs://RigName", "filtered": 147616, "date": 1536153189799, "unfiltered": 149920,
    "rssi": -64, "type": "sgv", "glucose": 109
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:08:09.901Z", "sgv": 108,
    "device": "xdripjs://RigName", "filtered": 144416, "date": 1536152889901, "unfiltered": 149344,
    "rssi": -68, "type": "sgv", "glucose": 108
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:03:09.901Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 140352, "date": 1536152589901, "unfiltered": 146144,
    "rssi": -79, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:58:09.936Z", "sgv": 102,
    "device": "xdripjs://RigName", "filtered": 136160, "date": 1536152289936, "unfiltered": 142656,
    "rssi": -66, "type": "sgv", "glucose": 102
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:53:10.044Z", "sgv": 99,
    "device": "xdripjs://RigName", "filtered": 132672, "date": 1536151990044, "unfiltered": 139520,
    "rssi": -63, "type": "sgv", "glucose": 99
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:48:09.862Z", "sgv": 94,
    "device": "xdripjs://RigName", "filtered": 130656, "date": 1536151689862, "unfiltered": 134080,
    "rssi": -63, "type": "sgv", "glucose": 94
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:43:09.861Z", "sgv": 92,
    "device": "xdripjs://RigName", "filtered": 130352, "date": 1536151389861, "unfiltered": 132192,
    "rssi": -63, "type": "sgv", "glucose": 92
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:38:09.979Z", "sgv": 90,
    "device": "xdripjs://RigName", "filtered": 131264, "date": 1536151089979, "unfiltered": 129952,
    "rssi": -52, "type": "sgv", "glucose": 90
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:33:10.038Z", "sgv": 89,
    "device": "xdripjs://RigName", "filtered": 132864, "date": 1536150790038, "unfiltered": 129792,
    "rssi": -78, "type": "sgv", "glucose": 89
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:28:09.991Z", "sgv": 92,
    "device": "xdripjs://RigName", "filtered": 134720, "date": 1536150489991, "unfiltered": 132320,
    "rssi": -68, "type": "sgv", "glucose": 92
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:23:10.111Z", "sgv": 93,
    "device": "xdripjs://RigName", "filtered": 136800, "date": 1536150190111, "unfiltered": 133952,
    "rssi": -67, "type": "sgv", "glucose": 93
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:18:10.020Z", "sgv": 95,
    "device": "xdripjs://RigName", "filtered": 138912, "date": 1536149890020, "unfiltered": 135488,
    "rssi": -68, "type": "sgv", "glucose": 95
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:13:10.039Z", "sgv": 97,
    "device": "xdripjs://RigName", "filtered": 140736, "date": 1536149590039, "unfiltered": 137376,
    "rssi": -70, "type": "sgv", "glucose": 97
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:08:10.426Z", "sgv": 99,
    "device": "xdripjs://RigName", "filtered": 142240, "date": 1536149290426, "unfiltered": 139808,
    "rssi": -71, "type": "sgv", "glucose": 99
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:03:10.079Z", "sgv": 101,
    "device": "xdripjs://RigName", "filtered": 143616, "date": 1536148990079, "unfiltered": 142208,
    "rssi": -71, "type": "sgv", "glucose": 101
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:58:10.242Z", "sgv": 102,
    "device": "xdripjs://RigName", "filtered": 145120, "date": 1536148690242, "unfiltered": 142752,
    "rssi": -73, "type": "sgv", "glucose": 102
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:53:10.255Z", "sgv": 103,
    "device": "xdripjs://RigName", "filtered": 146432, "date": 1536148390255, "unfiltered": 144128,
    "rssi": -73, "type": "sgv", "glucose": 103
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:48:09.968Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 147040, "date": 1536148089968, "unfiltered": 145568,
    "rssi": -85, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:43:09.969Z", "sgv": 106,
    "device": "xdripjs://RigName", "filtered": 146720, "date": 1536147789969, "unfiltered": 146592,
    "rssi": -82, "type": "sgv", "glucose": 106
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:38:09.562Z", "sgv": 106,
    "device": "xdripjs://RigName", "filtered": 145536, "date": 1536147489562, "unfiltered": 147296,
    "rssi": -82, "type": "sgv", "glucose": 106
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:28:10.085Z", "sgv": 104,
    "device": "xdripjs://RigName", "filtered": 141408, "date": 1536146890085, "unfiltered": 144672,
    "rssi": -76, "type": "sgv", "glucose": 104
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:23:10.839Z", "sgv": 102,
    "device": "xdripjs://RigName", "filtered": 138976, "date": 1536146590839, "unfiltered": 143040,
    "rssi": -76, "type": "sgv", "glucose": 102
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:18:11.253Z", "sgv": 99,
    "device": "xdripjs://RigName", "filtered": 136352, "date": 1536146291253, "unfiltered": 140160,
    "rssi": -87, "type": "sgv", "glucose": 99
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:13:11.320Z", "sgv": 97,
    "device": "xdripjs://RigName", "filtered": 133600, "date": 1536145991320, "unfiltered": 137600,
    "rssi": -77, "type": "sgv", "glucose": 97
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:08:11.297Z", "sgv": 95,
    "device": "xdripjs://RigName", "filtered": 130704, "date": 1536145691297, "unfiltered": 135584,
    "rssi": -82, "type": "sgv", "glucose": 95
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:03:11.327Z", "sgv": 92,
    "device": "xdripjs://RigName", "filtered": 127312, "date": 1536145391327, "unfiltered": 132000,
    "rssi": -77, "type": "sgv", "glucose": 92
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:58:11.318Z", "sgv": 88,
    "device": "xdripjs://RigName", "filtered": 123200, "date": 1536145091318, "unfiltered": 128544,
    "rssi": -81, "type": "sgv", "glucose": 88
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:53:11.283Z", "sgv": 86,
    "device": "xdripjs://RigName", "filtered": 118592, "date": 1536144791283, "unfiltered": 125808,
    "rssi": -71, "type": "sgv", "glucose": 86
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:48:11.181Z", "sgv": 81,
    "device": "xdripjs://RigName", "filtered": 113920, "date": 1536144491181, "unfiltered": 122160,
    "rssi": -76, "type": "sgv", "glucose": 81
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:43:11.297Z", "sgv": 74,
    "device": "xdripjs://RigName", "filtered": 109600, "date": 1536144191297, "unfiltered": 115712,
    "rssi": -72, "type": "sgv", "glucose": 74
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:38:11.116Z", "sgv": 70,
    "device": "xdripjs://RigName", "filtered": 105760, "date": 1536143891116, "unfiltered": 112048,
    "rssi": -69, "type": "sgv", "glucose": 70
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:33:11.211Z", "sgv": 66,
    "device": "xdripjs://RigName", "filtered": 102368, "date": 1536143591211, "unfiltered": 107984,
    "rssi": -79, "type": "sgv", "glucose": 66
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:28:11.364Z", "sgv": 62,
    "device": "xdripjs://RigName", "filtered": 99440, "date": 1536143291364, "unfiltered": 104128,
    "rssi": -76, "type": "sgv", "glucose": 62
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:23:11.353Z", "sgv": 58,
    "device": "xdripjs://RigName", "filtered": 96832, "date": 1536142991353, "unfiltered": 100528,
    "rssi": -76, "type": "sgv", "glucose": 58
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:18:11.230Z", "sgv": 56,
    "device": "xdripjs://RigName", "filtered": 94736, "date": 1536142691230, "unfiltered": 98288,
    "rssi": -75, "type": "sgv", "glucose": 56
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:13:10.540Z", "sgv": 54,
    "device": "xdripjs://RigName", "filtered": 93344, "date": 1536142390540, "unfiltered": 96560,
    "rssi": -69, "type": "sgv", "glucose": 54
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:08:11.212Z", "sgv": 51,
    "device": "xdripjs://RigName", "filtered": 92656, "date": 1536142091212, "unfiltered": 93616,
    "rssi": -72, "type": "sgv", "glucose": 51
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:03:11.347Z", "sgv": 49,
    "device": "xdripjs://RigName", "filtered": 92336, "date": 1536141791347, "unfiltered": 92496,
    "rssi": -76, "type": "sgv", "glucose": 49
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:58:11.231Z", "sgv": 50,
    "device": "xdripjs://RigName", "filtered": 92000, "date": 1536141491231, "unfiltered": 92672,
    "rssi": -89, "type": "sgv", "glucose": 50
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:53:11.299Z", "sgv": 49,
    "device": "xdripjs://RigName", "filtered": 91584, "date": 1536141191299, "unfiltered": 92048,
    "rssi": -84, "type": "sgv", "glucose": 49
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:48:11.391Z", "sgv": 49,
    "device": "xdripjs://RigName", "filtered": 91216, "date": 1536140891391, "unfiltered": 91968,
    "rssi": -88, "type": "sgv", "glucose": 49
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:43:11.504Z", "sgv": 48,
    "device": "xdripjs://RigName", "filtered": 90784, "date": 1536140591504, "unfiltered": 91664,
    "rssi": -85, "type": "sgv", "glucose": 48
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:38:11.679Z", "sgv": 47,
    "device": "xdripjs://RigName", "filtered": 89952, "date": 1536140291679, "unfiltered": 90640,
    "rssi": -92, "type": "sgv", "glucose": 47
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:33:11.262Z", "sgv": 46,
    "device": "xdripjs://RigName", "filtered": 88704, "date": 1536139991262, "unfiltered": 89792,
    "rssi": -86, "type": "sgv", "glucose": 46
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:28:11.439Z", "sgv": 47,
    "device": "xdripjs://RigName", "filtered": 87776, "date": 1536139691439, "unfiltered": 90224,
    "rssi": -90, "type": "sgv", "glucose": 47
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:23:10.725Z", "sgv": 46,
    "device": "xdripjs://RigName", "filtered": 88144, "date": 1536139390725, "unfiltered": 89520,
    "rssi": -86, "type": "sgv", "glucose": 46
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:13:10.924Z", "sgv": 45,
    "device": "xdripjs://RigName", "filtered": 92432, "date": 1536138790924, "unfiltered": 88160,
    "rssi": -79, "type": "sgv", "glucose": 45
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:08:11.372Z", "sgv": 47,
    "device": "xdripjs://RigName", "filtered": 94080, "date": 1536138491372, "unfiltered": 90176,
    "rssi": -78, "type": "sgv", "glucose": 47
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:03:11.511Z", "sgv": 50,
    "device": "xdripjs://RigName", "filtered": 95168, "date": 1536138191511, "unfiltered": 93200,
    "rssi": -78, "type": "sgv", "glucose": 50
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:58:11.357Z", "sgv": 54,
    "device": "xdripjs://RigName", "filtered": 96640, "date": 1536137891357, "unfiltered": 96624,
    "rssi": -78, "type": "sgv", "glucose": 54
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:53:11.464Z", "sgv": 53,
    "device": "xdripjs://RigName", "filtered": 99072, "date": 1536137591464, "unfiltered": 95840,
    "rssi": -78, "type": "sgv", "glucose": 53
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:48:11.320Z", "sgv": 54,
    "device": "xdripjs://RigName", "filtered": 101856, "date": 1536137291320, "unfiltered": 96560,
    "rssi": -85, "type": "sgv", "glucose": 54
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:43:11.359Z", "sgv": 57,
    "device": "xdripjs://RigName", "filtered": 104000, "date": 1536136991359, "unfiltered": 99648,
    "rssi": -77, "type": "sgv", "glucose": 57
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:38:10.748Z", "sgv": 61,
    "device": "xdripjs://RigName", "filtered": 105552, "date": 1536136690748, "unfiltered": 103424,
    "rssi": -95, "type": "sgv", "glucose": 61
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:33:10.839Z", "sgv": 64,
    "device": "xdripjs://RigName", "filtered": 107360, "date": 1536136390839, "unfiltered": 105696,
    "rssi": -79, "type": "sgv", "glucose": 64
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:28:11.487Z", "sgv": 65,
    "device": "xdripjs://RigName", "filtered": 109936, "date": 1536136091487, "unfiltered": 106592,
    "rssi": -78, "type": "sgv", "glucose": 65
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:23:11.156Z", "sgv": 66,
    "device": "xdripjs://RigName", "filtered": 112736, "date": 1536135791156, "unfiltered": 108096,
    "rssi": -95, "type": "sgv", "glucose": 66
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:18:11.285Z", "sgv": 68,
    "device": "xdripjs://RigName", "filtered": 115072, "date": 1536135491285, "unfiltered": 110016,
    "rssi": -98, "type": "sgv", "glucose": 68
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:13:10.975Z", "sgv": 73,
    "device": "xdripjs://RigName", "filtered": 116896, "date": 1536135190975, "unfiltered": 114544,
    "rssi": -77, "type": "sgv", "glucose": 73
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:08:10.733Z", "sgv": 76,
    "device": "xdripjs://RigName", "filtered": 118608, "date": 1536134890733, "unfiltered": 116928,
    "rssi": -69, "type": "sgv", "glucose": 76
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:53:10.547Z", "sgv": 82,
    "device": "xdripjs://RigName", "filtered": 126352, "date": 1536133990547, "unfiltered": 122864,
    "rssi": -51, "type": "sgv", "glucose": 82
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:48:10.633Z", "sgv": 82,
    "device": "xdripjs://RigName", "filtered": 129408, "date": 1536133690633, "unfiltered": 122928,
    "rssi": -57, "type": "sgv", "glucose": 82
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:43:10.464Z", "sgv": 89,
    "device": "xdripjs://RigName", "filtered": 132224, "date": 1536133390464, "unfiltered": 129216,
    "rssi": -67, "type": "sgv", "glucose": 89
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:38:10.477Z", "sgv": 90,
    "device": "xdripjs://RigName", "filtered": 134560, "date": 1536133090477, "unfiltered": 129952,
    "rssi": -64, "type": "sgv", "glucose": 90
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:33:10.581Z", "sgv": 93,
    "device": "xdripjs://RigName", "filtered": 136512, "date": 1536132790581, "unfiltered": 133568,
    "rssi": -70, "type": "sgv", "glucose": 93
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:28:10.505Z", "sgv": 95,
    "device": "xdripjs://RigName", "filtered": 138080, "date": 1536132490505, "unfiltered": 135488,
    "rssi": -56, "type": "sgv", "glucose": 95
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:23:10.519Z", "sgv": 97,
    "device": "xdripjs://RigName", "filtered": 139584, "date": 1536132190519, "unfiltered": 137824,
    "rssi": -50, "type": "sgv", "glucose": 97
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:18:10.472Z", "sgv": 98,
    "device": "xdripjs://RigName", "filtered": 141184, "date": 1536131890472, "unfiltered": 138560,
    "rssi": -50, "type": "sgv", "glucose": 98
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:13:10.606Z", "sgv": 100,
    "device": "xdripjs://RigName", "filtered": 142944, "date": 1536131590606, "unfiltered": 140448,
    "rssi": -55, "type": "sgv", "glucose": 100
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:08:10.637Z", "sgv": 101,
    "device": "xdripjs://RigName", "filtered": 144736, "date": 1536131290637, "unfiltered": 142016,
    "rssi": -57, "type": "sgv", "glucose": 101
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:03:10.549Z", "sgv": 103,
    "device": "xdripjs://RigName", "filtered": 146464, "date": 1536130990549, "unfiltered": 143520,
    "rssi": -49, "type": "sgv", "glucose": 103
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:58:10.848Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 148128, "date": 1536130690848, "unfiltered": 145760,
    "rssi": -56, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:53:10.609Z", "sgv": 106,
    "device": "xdripjs://RigName", "filtered": 149792, "date": 1536130390609, "unfiltered": 147424,
    "rssi": -53, "type": "sgv", "glucose": 106
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:48:11.252Z", "sgv": 108,
    "device": "xdripjs://RigName", "filtered": 151488, "date": 1536130091252, "unfiltered": 148864,
    "rssi": -57, "type": "sgv", "glucose": 108
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:43:10.667Z", "sgv": 109,
    "device": "xdripjs://RigName", "filtered": 153280, "date": 1536129790667, "unfiltered": 150496,
    "rssi": -55, "type": "sgv", "glucose": 109
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:38:10.877Z", "sgv": 111,
    "device": "xdripjs://RigName", "filtered": 155232, "date": 1536129490877, "unfiltered": 152512,
    "rssi": -54, "type": "sgv", "glucose": 111
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:33:10.592Z", "sgv": 113,
    "device": "xdripjs://RigName", "filtered": 157472, "date": 1536129190592, "unfiltered": 154272,
    "rssi": -51, "type": "sgv", "glucose": 113
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:28:10.501Z", "sgv": 115,
    "device": "xdripjs://RigName", "filtered": 160032, "date": 1536128890501, "unfiltered": 156416,
    "rssi": -50, "type": "sgv", "glucose": 115
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:23:10.560Z", "sgv": 117,
    "device": "xdripjs://RigName", "filtered": 162560, "date": 1536128590560, "unfiltered": 158496,
    "rssi": -50, "type": "sgv", "glucose": 117
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:18:11.011Z", "sgv": 119,
    "device": "xdripjs://RigName", "filtered": 164704, "date": 1536128291011, "unfiltered": 160672,
    "rssi": -51, "type": "sgv", "glucose": 119
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:13:11.025Z", "sgv": 122,
    "device": "xdripjs://RigName", "filtered": 166368, "date": 1536127991025, "unfiltered": 163904,
    "rssi": -52, "type": "sgv", "glucose": 122
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:08:10.753Z", "sgv": 124,
    "device": "xdripjs://RigName", "filtered": 167840, "date": 1536127690753, "unfiltered": 166016,
    "rssi": -60, "type": "sgv", "glucose": 124
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:03:10.572Z", "sgv": 125,
    "device": "xdripjs://RigName", "filtered": 169376, "date": 1536127390572, "unfiltered": 166976,
    "rssi": -54, "type": "sgv", "glucose": 125
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:58:10.631Z", "sgv": 127,
    "device": "xdripjs://RigName", "filtered": 171072, "date": 1536127090631, "unfiltered": 168512,
    "rssi": -57, "type": "sgv", "glucose": 127
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:53:10.690Z", "sgv": 129,
    "device": "xdripjs://RigName", "filtered": 172896, "date": 1536126790690, "unfiltered": 170368,
    "rssi": -53, "type": "sgv", "glucose": 129
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:48:11.064Z", "sgv": 130,
    "device": "xdripjs://RigName", "filtered": 174944, "date": 1536126491064, "unfiltered": 171904,
    "rssi": -51, "type": "sgv", "glucose": 130
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:43:10.792Z", "sgv": 132,
    "device": "xdripjs://RigName", "filtered": 177088, "date": 1536126190792, "unfiltered": 174016,
    "rssi": -52, "type": "sgv", "glucose": 132
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:38:10.790Z", "sgv": 134,
    "device": "xdripjs://RigName", "filtered": 179008, "date": 1536125890790, "unfiltered": 175488,
    "rssi": -52, "type": "sgv", "glucose": 134
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:33:10.999Z", "sgv": 136,
    "device": "xdripjs://RigName", "filtered": 180576, "date": 1536125590999, "unfiltered": 178048,
    "rssi": -52, "type": "sgv", "glucose": 136
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:28:10.699Z", "sgv": 138,
    "device": "xdripjs://RigName", "filtered": 181792, "date": 1536125290699, "unfiltered": 180032,
    "rssi": -54, "type": "sgv", "glucose": 138
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:23:10.935Z", "sgv": 139,
    "device": "xdripjs://RigName", "filtered": 183008, "date": 1536124990935, "unfiltered": 181184,
    "rssi": -53, "type": "sgv", "glucose": 139
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:18:10.814Z", "sgv": 141,
    "device": "xdripjs://RigName", "filtered": 184352, "date": 1536124690814, "unfiltered": 182880,
    "rssi": -51, "type": "sgv", "glucose": 141
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:13:10.767Z", "sgv": 141,
    "device": "xdripjs://RigName", "filtered": 185664, "date": 1536124390767, "unfiltered": 183328,
    "rssi": -51, "type": "sgv", "glucose": 141
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:08:10.782Z", "sgv": 142,
    "device": "xdripjs://RigName", "filtered": 186720, "date": 1536124090782, "unfiltered": 184512,
    "rssi": -54, "type": "sgv", "glucose": 142
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:03:10.854Z", "sgv": 144,
    "device": "xdripjs://RigName", "filtered": 187552, "date": 1536123790854, "unfiltered": 186592,
    "rssi": -51, "type": "sgv", "glucose": 144
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:58:10.778Z", "sgv": 145,
    "device": "xdripjs://RigName", "filtered": 188512, "date": 1536123490778, "unfiltered": 187200,
    "rssi": -52, "type": "sgv", "glucose": 145
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:53:10.793Z", "sgv": 146,
    "device": "xdripjs://RigName", "filtered": 190016, "date": 1536123190793, "unfiltered": 188576,
    "rssi": -51, "type": "sgv", "glucose": 146
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:48:10.792Z", "sgv": 147,
    "device": "xdripjs://RigName", "filtered": 191936, "date": 1536122890792, "unfiltered": 189056,
    "rssi": -64, "type": "sgv", "glucose": 147
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:43:10.716Z", "sgv": 148,
    "device": "xdripjs://RigName", "filtered": 193856, "date": 1536122590716, "unfiltered": 190240,
    "rssi": -68, "type": "sgv", "glucose": 148
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:38:10.970Z", "sgv": 150,
    "device": "xdripjs://RigName", "filtered": 195424, "date": 1536122290970, "unfiltered": 192832,
    "rssi": -59, "type": "sgv", "glucose": 150
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:33:11.224Z", "sgv": 153,
    "device": "xdripjs://RigName", "filtered": 196256, "date": 1536121991224, "unfiltered": 195360,
    "rssi": -58, "type": "sgv", "glucose": 153
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:28:10.745Z", "sgv": 152,
    "device": "xdripjs://RigName", "filtered": 196288, "date": 1536121690745, "unfiltered": 194720,
    "rssi": -64, "type": "sgv", "glucose": 152
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:23:10.880Z", "sgv": 154,
    "device": "xdripjs://RigName", "filtered": 195776, "date": 1536121390880, "unfiltered": 197088,
    "rssi": -91, "type": "sgv", "glucose": 154
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:18:10.865Z", "sgv": 154,
    "device": "xdripjs://RigName", "filtered": 195296, "date": 1536121090865, "unfiltered": 196576,
    "rssi": -64, "type": "sgv", "glucose": 154
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:13:11.119Z", "sgv": 153,
    "device": "xdripjs://RigName", "filtered": 195488, "date": 1536120791119, "unfiltered": 195968,
    "rssi": -76, "type": "sgv", "glucose": 153
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:08:10.803Z", "sgv": 152,
    "device": "xdripjs://RigName", "filtered": 196352, "date": 1536120490803, "unfiltered": 195040,
    "rssi": -57, "type": "sgv", "glucose": 152
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:03:11.269Z", "sgv": 153,
    "device": "xdripjs://RigName", "filtered": 197408, "date": 1536120191269, "unfiltered": 195648,
    "rssi": -65, "type": "sgv", "glucose": 153
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:58:11.192Z", "sgv": 154,
    "device": "xdripjs://RigName", "filtered": 198016, "date": 1536119891192, "unfiltered": 196608,
    "rssi": -63, "type": "sgv", "glucose": 154
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:53:10.909Z", "sgv": 155,
    "device": "xdripjs://RigName", "filtered": 197952, "date": 1536119590909, "unfiltered": 197536,
    "rssi": -73, "type": "sgv", "glucose": 155
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:48:11.011Z", "sgv": 156,
    "device": "xdripjs://RigName", "filtered": 197280, "date": 1536119291011, "unfiltered": 198432,
    "rssi": -72, "type": "sgv", "glucose": 156
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:43:11.038Z", "sgv": 155,
    "device": "xdripjs://RigName", "filtered": 195968, "date": 1536118991038, "unfiltered": 197952,
    "rssi": -58, "type": "sgv", "glucose": 155
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:38:10.939Z", "sgv": 154,
    "device": "xdripjs://RigName", "filtered": 193856, "date": 1536118690939, "unfiltered": 196256,
    "rssi": -57, "type": "sgv", "glucose": 154
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:33:10.884Z", "sgv": 153,
    "device": "xdripjs://RigName", "filtered": 190688, "date": 1536118390884, "unfiltered": 195136,
    "rssi": -69, "type": "sgv", "glucose": 153
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:28:12.033Z", "sgv": 150,
    "device": "xdripjs://RigName", "filtered": 186880, "date": 1536118092033, "unfiltered": 192224,
    "rssi": -77, "type": "sgv", "glucose": 150
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:23:12.090Z", "sgv": 148,
    "device": "xdripjs://RigName", "filtered": 183232, "date": 1536117792090, "unfiltered": 190368,
    "rssi": -82, "type": "sgv", "glucose": 148
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:18:12.359Z", "sgv": 143,
    "device": "xdripjs://RigName", "filtered": 180256, "date": 1536117492359, "unfiltered": 185120,
    "rssi": -77, "type": "sgv", "glucose": 143
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:13:12.087Z", "sgv": 139,
    "device": "xdripjs://RigName", "filtered": 178016, "date": 1536117192087, "unfiltered": 181280,
    "rssi": -67, "type": "sgv", "glucose": 139
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:08:12.073Z", "sgv": 137,
    "device": "xdripjs://RigName", "filtered": 175776, "date": 1536116892073, "unfiltered": 179456,
    "rssi": -58, "type": "sgv", "glucose": 137
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:03:12.283Z", "sgv": 134,
    "device": "xdripjs://RigName", "filtered": 173152, "date": 1536116592283, "unfiltered": 175872,
    "rssi": -66, "type": "sgv", "glucose": 134
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:58:11.992Z", "sgv": 133,
    "device": "xdripjs://RigName", "filtered": 170016, "date": 1536116291992, "unfiltered": 175360,
    "rssi": -59, "type": "sgv", "glucose": 133
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:53:12.142Z", "sgv": 130,
    "device": "xdripjs://RigName", "filtered": 166656, "date": 1536115992142, "unfiltered": 171776,
    "rssi": -76, "type": "sgv", "glucose": 130
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:48:12.022Z", "sgv": 127,
    "device": "xdripjs://RigName", "filtered": 163616, "date": 1536115692022, "unfiltered": 168672,
    "rssi": -64, "type": "sgv", "glucose": 127
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:43:11.927Z", "sgv": 124,
    "device": "xdripjs://RigName", "filtered": 160544, "date": 1536115391927, "unfiltered": 165824,
    "rssi": -73, "type": "sgv", "glucose": 124
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:38:12.227Z", "sgv": 119,
    "device": "xdripjs://RigName", "filtered": 157120, "date": 1536115092227, "unfiltered": 160480,
    "rssi": -72, "type": "sgv", "glucose": 119
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:33:12.030Z", "sgv": 118,
    "device": "xdripjs://RigName", "filtered": 153600, "date": 1536114792030, "unfiltered": 159744,
    "rssi": -66, "type": "sgv", "glucose": 118
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:28:12.254Z", "sgv": 115,
    "device": "xdripjs://RigName", "filtered": 150400, "date": 1536114492254, "unfiltered": 156736,
    "rssi": -70, "type": "sgv", "glucose": 115
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:23:11.981Z", "sgv": 110,
    "device": "xdripjs://RigName", "filtered": 147744, "date": 1536114191981, "unfiltered": 151488,
    "rssi": -60, "type": "sgv", "glucose": 110
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:18:12.071Z", "sgv": 108,
    "device": "xdripjs://RigName", "filtered": 145024, "date": 1536113892071, "unfiltered": 148544,
    "rssi": -70, "type": "sgv", "glucose": 108
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:13:12.085Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 142496, "date": 1536113592085, "unfiltered": 145664,
    "rssi": -62, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:08:12.263Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 142048, "date": 1536113292263, "unfiltered": 145728,
    "rssi": -63, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:03:12.202Z", "sgv": 103,
    "device": "xdripjs://RigName", "filtered": 145696, "date": 1536112992202, "unfiltered": 144000,
    "rssi": -65, "type": "sgv", "glucose": 103
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:58:11.592Z", "sgv": 102,
    "device": "xdripjs://RigName", "filtered": 153632, "date": 1536112691592, "unfiltered": 142784,
    "rssi": -77, "type": "sgv", "glucose": 102
  }, {
    "direction": "SingleDown", "noise": 1, "dateString": "2018-09-05T01:53:11.560Z", "sgv": 106,
    "device": "xdripjs://RigName", "filtered": 164032, "date": 1536112391560, "unfiltered": 146912,
    "rssi": -79, "type": "sgv", "glucose": 106
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:48:12.182Z", "sgv": 117,
    "device": "xdripjs://RigName", "filtered": 174240, "date": 1536112092182, "unfiltered": 157952,
    "rssi": -62, "type": "sgv", "glucose": 117
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:43:12.060Z", "sgv": 126,
    "device": "xdripjs://RigName", "filtered": 183072, "date": 1536111792060, "unfiltered": 167456,
    "rssi": -73, "type": "sgv", "glucose": 126
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:38:12.059Z", "sgv": 138,
    "device": "xdripjs://RigName", "filtered": 190400, "date": 1536111492059, "unfiltered": 180224,
    "rssi": -62, "type": "sgv", "glucose": 138
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:33:12.042Z", "sgv": 145,
    "device": "xdripjs://RigName", "filtered": 196000, "date": 1536111192042, "unfiltered": 186784,
    "rssi": -71, "type": "sgv", "glucose": 145
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:28:12.175Z", "sgv": 149,
    "device": "xdripjs://RigName", "filtered": 199616, "date": 1536110892175, "unfiltered": 191712,
    "rssi": -85, "type": "sgv", "glucose": 149
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:23:12.144Z", "sgv": 156,
    "device": "xdripjs://RigName", "filtered": 200896, "date": 1536110592144, "unfiltered": 198528,
    "rssi": -70, "type": "sgv", "glucose": 156
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:18:12.308Z", "sgv": 158,
    "device": "xdripjs://RigName", "filtered": 199968, "date": 1536110292308, "unfiltered": 201216,
    "rssi": -80, "type": "sgv", "glucose": 158
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:13:11.774Z", "sgv": 158,
    "device": "xdripjs://RigName", "filtered": 196384, "date": 1536109991774, "unfiltered": 201120,
    "rssi": -60, "type": "sgv", "glucose": 158
  }, {
    "direction": "FortyFiveUp", "noise": 1, "dateString": "2018-09-05T01:08:12.100Z", "sgv": 154,
    "device": "xdripjs://RigName", "filtered": 189152, "date": 1536109692100, "unfiltered": 196224,
    "rssi": -65, "type": "sgv", "glucose": 154
  }, {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T01:03:11.375Z", "sgv": 152,
    "device": "xdripjs://RigName", "filtered": 177856, "date": 1536109391375, "unfiltered": 194080,
    "rssi": -62, "type": "sgv", "glucose": 152
  }, {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T00:58:11.403Z", "sgv": 144,
    "device": "xdripjs://RigName", "filtered": 162752, "date": 1536109091403, "unfiltered": 185920,
    "rssi": -64, "type": "sgv", "glucose": 144
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T00:53:11.449Z", "sgv": 129,
    "device": "xdripjs://RigName", "filtered": 144448, "date": 1536108791449, "unfiltered": 170400,
    "rssi": -74, "type": "sgv", "glucose": 129
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T00:48:11.417Z", "sgv": 112,
    "device": "xdripjs://RigName", "filtered": 124656, "date": 1536108491417, "unfiltered": 153120,
    "rssi": -69, "type": "sgv", "glucose": 112
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T00:43:11.384Z", "sgv": 98,
    "device": "xdripjs://RigName", "filtered": 107120, "date": 1536108191384, "unfiltered": 138976,
    "rssi": -76, "type": "sgv", "glucose": 98
  }, {
    "direction": "FortyFiveUp", "noise": 1, "dateString": "2018-09-05T00:38:11.985Z", "sgv": 79,
    "device": "xdripjs://RigName", "filtered": 95520, "date": 1536107891985, "unfiltered": 119904,
    "rssi": -67, "type": "sgv", "glucose": 79
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:33:12.181Z", "sgv": 57,
    "device": "xdripjs://RigName", "filtered": 90672, "date": 1536107592181, "unfiltered": 99104,
    "rssi": -68, "type": "sgv", "glucose": 57
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:28:11.742Z", "sgv": 46,
    "device": "xdripjs://RigName", "filtered": 90400, "date": 1536107291742, "unfiltered": 89728,
    "rssi": -63, "type": "sgv", "glucose": 46
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:23:11.454Z", "sgv": 47,
    "device": "xdripjs://RigName", "filtered": 92208, "date": 1536106991454, "unfiltered": 90352,
    "rssi": -66, "type": "sgv", "glucose": 47
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:18:11.331Z", "sgv": 48,
    "device": "xdripjs://RigName", "filtered": 95248, "date": 1536106691331, "unfiltered": 90992,
    "rssi": -71, "type": "sgv", "glucose": 48
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:13:11.389Z", "sgv": 50,
    "device": "xdripjs://RigName", "filtered": 99440, "date": 1536106391389, "unfiltered": 93264,
    "rssi": -59, "type": "sgv", "glucose": 50
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:08:11.701Z", "sgv": 55,
    "device": "xdripjs://RigName", "filtered": 104176, "date": 1536106091701, "unfiltered": 97680,
    "rssi": -72, "type": "sgv", "glucose": 55
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:03:12.207Z", "sgv": 58,
    "device": "xdripjs://RigName", "filtered": 108672, "date": 1536105792207, "unfiltered": 100336,
    "rssi": -62, "type": "sgv", "glucose": 58
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:58:11.352Z", "sgv": 64,
    "device": "xdripjs://RigName", "filtered": 111984, "date": 1536105491352, "unfiltered": 106400,
    "rssi": -75, "type": "sgv", "glucose": 64
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:53:11.659Z", "sgv": 68,
    "device": "xdripjs://RigName", "filtered": 113744, "date": 1536105191659, "unfiltered": 109840,
    "rssi": -70, "type": "sgv", "glucose": 68
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:48:11.323Z", "sgv": 72,
    "device": "xdripjs://RigName", "filtered": 114528, "date": 1536104891323, "unfiltered": 113648,
    "rssi": -63, "type": "sgv", "glucose": 72
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:43:11.446Z", "sgv": 74,
    "device": "xdripjs://RigName", "filtered": 114944, "date": 1536104591446, "unfiltered": 115008,
    "rssi": -66, "type": "sgv", "glucose": 74
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:38:11.473Z", "sgv": 73,
    "device": "xdripjs://RigName", "filtered": 115520, "date": 1536104291473, "unfiltered": 114272,
    "rssi": -70, "type": "sgv", "glucose": 73
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:33:11.363Z", "sgv": 74,
    "device": "xdripjs://RigName", "filtered": 116528, "date": 1536103991363, "unfiltered": 115376,
    "rssi": -76, "type": "sgv", "glucose": 74
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:28:11.370Z", "sgv": 75,
    "device": "xdripjs://RigName", "filtered": 118288, "date": 1536103691370, "unfiltered": 116176,
    "rssi": -73, "type": "sgv", "glucose": 75
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:23:11.380Z", "sgv": 76,
    "device": "xdripjs://RigName", "filtered": 121648, "date": 1536103391380, "unfiltered": 117344,
    "rssi": -70, "type": "sgv", "glucose": 76
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T23:18:11.383Z", "sgv": 80,
    "device": "xdripjs://RigName", "filtered": 127376, "date": 1536103091383, "unfiltered": 120448,
    "rssi": -73, "type": "sgv", "glucose": 80
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T23:13:11.327Z", "sgv": 84,
    "device": "xdripjs://RigName", "filtered": 135008, "date": 1536102791327, "unfiltered": 124880,
    "rssi": -73, "type": "sgv", "glucose": 84
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T23:08:11.409Z", "sgv": 88,
    "device": "xdripjs://RigName", "filtered": 142464, "date": 1536102491409, "unfiltered": 128784,
    "rssi": -68, "type": "sgv", "glucose": 88
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:03:11.428Z", "sgv": 96,
    "device": "xdripjs://RigName", "filtered": 147328, "date": 1536102191428, "unfiltered": 136288,
    "rssi": -69, "type": "sgv", "glucose": 96
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:58:11.490Z", "sgv": 105,
    "device": "xdripjs://RigName", "filtered": 148896, "date": 1536101891490, "unfiltered": 145920,
    "rssi": -70, "type": "sgv", "glucose": 105
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:53:11.708Z", "sgv": 109,
    "device": "xdripjs://RigName", "filtered": 148576, "date": 1536101591708, "unfiltered": 149824,
    "rssi": -75, "type": "sgv", "glucose": 109
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:48:11.420Z", "sgv": 109,
    "device": "xdripjs://RigName", "filtered": 148320, "date": 1536101291420, "unfiltered": 149664,
    "rssi": -66, "type": "sgv", "glucose": 109
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:43:11.464Z", "sgv": 108,
    "device": "xdripjs://RigName", "filtered": 148960, "date": 1536100991464, "unfiltered": 148768,
    "rssi": -73, "type": "sgv", "glucose": 108
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:38:11.520Z", "sgv": 107,
    "device": "xdripjs://RigName", "filtered": 150432, "date": 1536100691520, "unfiltered": 148128,
    "rssi": -67, "type": "sgv", "glucose": 107
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:33:11.790Z", "sgv": 108,
    "device": "xdripjs://RigName", "filtered": 152288, "date": 1536100391790, "unfiltered": 149184,
    "rssi": -82, "type": "sgv", "glucose": 108
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:28:11.471Z", "sgv": 110,
    "device": "xdripjs://RigName", "filtered": 154432, "date": 1536100091471, "unfiltered": 151168,
    "rssi": -63, "type": "sgv", "glucose": 110
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:23:11.936Z", "sgv": 112,
    "device": "xdripjs://RigName", "filtered": 157600, "date": 1536099791936, "unfiltered": 153696,
    "rssi": -88, "type": "sgv", "glucose": 112
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:18:11.528Z", "sgv": 116,
    "device": "xdripjs://RigName", "filtered": 162496, "date": 1536099491528, "unfiltered": 156896,
    "rssi": -67, "type": "sgv", "glucose": 116
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T22:13:11.601Z", "sgv": 118,
    "device": "xdripjs://RigName", "filtered": 169344, "date": 1536099191601, "unfiltered": 159136,
    "rssi": -59, "type": "sgv", "glucose": 118
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T22:08:11.764Z", "sgv": 124,
    "device": "xdripjs://RigName", "filtered": 177248, "date": 1536098891764, "unfiltered": 165600,
    "rssi": -65, "type": "sgv", "glucose": 124
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T22:03:11.642Z", "sgv": 130,
    "device": "xdripjs://RigName", "filtered": 184608, "date": 1536098591642, "unfiltered": 171712,
    "rssi": -65, "type": "sgv", "glucose": 130
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T21:58:11.655Z", "sgv": 138,
    "device": "xdripjs://RigName", "filtered": 190368, "date": 1536098291655, "unfiltered": 180096,
    "rssi": -69, "type": "sgv", "glucose": 138
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:53:11.459Z", "sgv": 146,
    "device": "xdripjs://RigName", "filtered": 193984, "date": 1536097991459, "unfiltered": 188384,
    "rssi": -68, "type": "sgv", "glucose": 146
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:48:11.787Z", "sgv": 149,
    "device": "xdripjs://RigName", "filtered": 196224, "date": 1536097691787, "unfiltered": 191328,
    "rssi": -79, "type": "sgv", "glucose": 149
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:43:11.575Z", "sgv": 154,
    "device": "xdripjs://RigName", "filtered": 198592, "date": 1536097391575, "unfiltered": 196832,
    "rssi": -66, "type": "sgv", "glucose": 154
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:38:11.651Z", "sgv": 156,
    "device": "xdripjs://RigName", "filtered": 202432, "date": 1536097091651, "unfiltered": 198464,
    "rssi": -52, "type": "sgv", "glucose": 156
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:33:11.500Z", "sgv": 157,
    "device": "xdripjs://RigName", "filtered": 208032, "date": 1536096791500, "unfiltered": 199936,
    "rssi": -58, "type": "sgv", "glucose": 157
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T21:28:11.510Z", "sgv": 161,
    "device": "xdripjs://RigName", "filtered": 214336, "date": 1536096491510, "unfiltered": 203648,
    "rssi": -54, "type": "sgv", "glucose": 161
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:23:11.882Z", "sgv": 168,
    "device": "xdripjs://RigName", "filtered": 219456, "date": 1536096191882, "unfiltered": 211264,
    "rssi": -72, "type": "sgv", "glucose": 168
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:18:11.618Z", "sgv": 172,
    "device": "xdripjs://RigName", "filtered": 222368, "date": 1536095891618, "unfiltered": 214720,
    "rssi": -58, "type": "sgv", "glucose": 172
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:13:11.822Z", "sgv": 178,
    "device": "xdripjs://RigName", "filtered": 224288, "date": 1536095591822, "unfiltered": 221792,
    "rssi": -73, "type": "sgv", "glucose": 178
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:08:11.851Z", "sgv": 184,
    "device": "xdripjs://RigName", "filtered": 227200, "date": 1536095291851, "unfiltered": 227168,
    "rssi": -55, "type": "sgv", "glucose": 184
  }, {
    "direction": "Flat", "noise": 4, "dateString": "2018-09-04T21:03:12.298Z", "sgv": 181,
    "device": "xdripjs://RigName", "filtered": 232288, "date": 1536094992298, "unfiltered": 224512,
    "rssi": -57, "type": "sgv", "glucose": 181
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:28:11.686Z", "sgv": 215,
    "device": "xdripjs://RigName", "filtered": 260704, "date": 1536092891686, "unfiltered": 259936,
    "rssi": -44, "type": "sgv", "glucose": 215
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:23:11.985Z", "sgv": 213,
    "device": "xdripjs://RigName", "filtered": 261504, "date": 1536092591985, "unfiltered": 258080,
    "rssi": -48, "type": "sgv", "glucose": 213
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:18:11.642Z", "sgv": 216,
    "device": "xdripjs://RigName", "filtered": 260960, "date": 1536092291642, "unfiltered": 260992,
    "rssi": -59, "type": "sgv", "glucose": 216
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:13:11.834Z", "sgv": 217,
    "device": "xdripjs://RigName", "filtered": 259648, "date": 1536091991834, "unfiltered": 261504,
    "rssi": -72, "type": "sgv", "glucose": 217
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:08:11.774Z", "sgv": 218,
    "device": "xdripjs://RigName", "filtered": 259456, "date": 1536091691774, "unfiltered": 262272,
    "rssi": -53, "type": "sgv", "glucose": 218
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:03:11.758Z", "sgv": 216,
    "device": "xdripjs://RigName", "filtered": 261088, "date": 1536091391758, "unfiltered": 260864,
    "rssi": -74, "type": "sgv", "glucose": 216
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:58:11.714Z", "sgv": 213,
    "device": "xdripjs://RigName", "filtered": 263680, "date": 1536091091714, "unfiltered": 257440,
    "rssi": -64, "type": "sgv", "glucose": 213
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:53:12.100Z", "sgv": 217,
    "device": "xdripjs://RigName", "filtered": 266048, "date": 1536090792100, "unfiltered": 261504,
    "rssi": -64, "type": "sgv", "glucose": 217
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:48:11.859Z", "sgv": 221,
    "device": "xdripjs://RigName", "filtered": 267520, "date": 1536090491859, "unfiltered": 266176,
    "rssi": -53, "type": "sgv", "glucose": 221
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:43:11.739Z", "sgv": 222,
    "device": "xdripjs://RigName", "filtered": 268416, "date": 1536090191739, "unfiltered": 267008,
    "rssi": -57, "type": "sgv", "glucose": 222
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:38:11.872Z", "sgv": 222,
    "device": "xdripjs://RigName", "filtered": 268416, "date": 1536089891872, "unfiltered": 267200,
    "rssi": -58, "type": "sgv", "glucose": 222
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:33:12.502Z", "sgv": 223,
    "device": "xdripjs://RigName", "filtered": 267584, "date": 1536089592502, "unfiltered": 268288,
    "rssi": -79, "type": "sgv", "glucose": 223
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:28:12.875Z", "sgv": 224,
    "device": "xdripjs://RigName", "filtered": 266624, "date": 1536089292875, "unfiltered": 269248,
    "rssi": -77, "type": "sgv", "glucose": 224
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:23:12.748Z", "sgv": 223,
    "device": "xdripjs://RigName", "filtered": 266432, "date": 1536088992748, "unfiltered": 267968,
    "rssi": -54, "type": "sgv", "glucose": 223
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:18:12.777Z", "sgv": 221,
    "device": "xdripjs://RigName", "filtered": 266688, "date": 1536088692777, "unfiltered": 265984,
    "rssi": -52, "type": "sgv", "glucose": 221
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:13:12.810Z", "sgv": 220,
    "device": "xdripjs://RigName", "filtered": 266880, "date": 1536088392810, "unfiltered": 265216,
    "rssi": -58, "type": "sgv", "glucose": 220
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:08:12.864Z", "sgv": 223,
    "device": "xdripjs://RigName", "filtered": 266624, "date": 1536088092864, "unfiltered": 267648,
    "rssi": -62, "type": "sgv", "glucose": 223
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:03:13.028Z", "sgv": 223,
    "device": "xdripjs://RigName", "filtered": 266048, "date": 1536087793028, "unfiltered": 267520,
    "rssi": -48, "type": "sgv", "glucose": 223
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:58:12.876Z", "sgv": 221,
    "device": "xdripjs://RigName", "filtered": 265280, "date": 1536087492876, "unfiltered": 265600,
    "rssi": -50, "type": "sgv", "glucose": 221
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:53:12.769Z", "sgv": 221,
    "device": "xdripjs://RigName", "filtered": 264256, "date": 1536087192769, "unfiltered": 265984,
    "rssi": -48, "type": "sgv", "glucose": 221
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:48:12.917Z", "sgv": 221,
    "device": "xdripjs://RigName", "filtered": 262720, "date": 1536086892917, "unfiltered": 265472,
    "rssi": -47, "type": "sgv", "glucose": 221
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:43:12.796Z", "sgv": 218,
    "device": "xdripjs://RigName", "filtered": 260160, "date": 1536086592796, "unfiltered": 262912,
    "rssi": -49, "type": "sgv", "glucose": 218
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:38:12.988Z", "sgv": 216,
    "device": "xdripjs://RigName", "filtered": 256288, "date": 1536086292988, "unfiltered": 260864,
    "rssi": -49, "type": "sgv", "glucose": 216
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:33:13.041Z", "sgv": 215,
    "device": "xdripjs://RigName", "filtered": 251584, "date": 1536085993041, "unfiltered": 259520,
    "rssi": -67, "type": "sgv", "glucose": 215
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:28:13.105Z", "sgv": 211,
    "device": "xdripjs://RigName", "filtered": 246880, "date": 1536085693105, "unfiltered": 255360,
    "rssi": -80, "type": "sgv", "glucose": 211
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:23:12.936Z", "sgv": 204,
    "device": "xdripjs://RigName", "filtered": 242560, "date": 1536085392936, "unfiltered": 248608,
    "rssi": -70, "type": "sgv", "glucose": 204
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:18:12.919Z", "sgv": 200,
    "device": "xdripjs://RigName", "filtered": 238496, "date": 1536085092919, "unfiltered": 244384,
    "rssi": -50, "type": "sgv", "glucose": 200
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:13:13.117Z", "sgv": 197,
    "device": "xdripjs://RigName", "filtered": 234720, "date": 1536084793117, "unfiltered": 241344,
    "rssi": -62, "type": "sgv", "glucose": 197
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:08:12.990Z", "sgv": 193,
    "device": "xdripjs://RigName", "filtered": 231232, "date": 1536084492990, "unfiltered": 236992,
    "rssi": -53, "type": "sgv", "glucose": 193
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:03:12.838Z", "sgv": 189,
    "device": "xdripjs://RigName", "filtered": 227680, "date": 1536084192838, "unfiltered": 232448,
    "rssi": -54, "type": "sgv", "glucose": 189
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:58:13.094Z", "sgv": 185,
    "device": "xdripjs://RigName", "filtered": 223840, "date": 1536083893094, "unfiltered": 228896,
    "rssi": -65, "type": "sgv", "glucose": 185
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:53:13.029Z", "sgv": 184,
    "device": "xdripjs://RigName", "filtered": 219616, "date": 1536083593029, "unfiltered": 227424,
    "rssi": -65, "type": "sgv", "glucose": 184
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:48:12.256Z", "sgv": 178,
    "device": "xdripjs://RigName", "filtered": 215008, "date": 1536083292256, "unfiltered": 221024,
    "rssi": -65, "type": "sgv", "glucose": 178
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:43:13.039Z", "sgv": 174,
    "device": "xdripjs://RigName", "filtered": 209920, "date": 1536082993039, "unfiltered": 217408,
    "rssi": -60, "type": "sgv", "glucose": 174
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:38:12.517Z", "sgv": 170,
    "device": "xdripjs://RigName", "filtered": 204320, "date": 1536082692517, "unfiltered": 212992,
    "rssi": -62, "type": "sgv", "glucose": 170
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:33:13.110Z", "sgv": 165,
    "device": "xdripjs://RigName", "filtered": 198944, "date": 1536082393110, "unfiltered": 207552,
    "rssi": -62, "type": "sgv", "glucose": 165
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:28:13.003Z", "sgv": 159,
    "device": "xdripjs://RigName", "filtered": 194624, "date": 1536082093003, "unfiltered": 202240,
    "rssi": -61, "type": "sgv", "glucose": 159
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:23:12.286Z", "sgv": 155,
    "device": "xdripjs://RigName", "filtered": 191552, "date": 1536081792286, "unfiltered": 197728,
    "rssi": -55, "type": "sgv", "glucose": 155
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:18:12.226Z", "sgv": 149,
    "device": "xdripjs://RigName", "filtered": 189312, "date": 1536081492226, "unfiltered": 191648,
    "rssi": -66, "type": "sgv", "glucose": 149
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:13:12.596Z", "sgv": 148,
    "device": "xdripjs://RigName", "filtered": 187136, "date": 1536081192596, "unfiltered": 190304,
    "rssi": -54, "type": "sgv", "glucose": 148
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:08:12.934Z", "sgv": 146,
    "device": "xdripjs://RigName", "filtered": 184768, "date": 1536080892934, "unfiltered": 188480,
    "rssi": -54, "type": "sgv", "glucose": 146
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:03:12.947Z", "sgv": 144,
    "device": "xdripjs://RigName", "filtered": 182432, "date": 1536080592947, "unfiltered": 186560,
    "rssi": -49, "type": "sgv", "glucose": 144
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:58:12.991Z", "sgv": 141,
    "device": "xdripjs://RigName", "filtered": 179968, "date": 1536080292991, "unfiltered": 183520,
    "rssi": -70, "type": "sgv", "glucose": 141
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:53:13.079Z", "sgv": 139,
    "device": "xdripjs://RigName", "filtered": 177280, "date": 1536079993079, "unfiltered": 180608,
    "rssi": -56, "type": "sgv", "glucose": 139
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:48:13.092Z", "sgv": 137,
    "device": "xdripjs://RigName", "filtered": 174592, "date": 1536079693092, "unfiltered": 179360,
    "rssi": -76, "type": "sgv", "glucose": 137
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:43:13.045Z", "sgv": 135,
    "device": "xdripjs://RigName", "filtered": 172352, "date": 1536079393045, "unfiltered": 176736,
    "rssi": -65, "type": "sgv", "glucose": 135
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:38:12.329Z", "sgv": 131,
    "device": "xdripjs://RigName", "filtered": 170368, "date": 1536079092329, "unfiltered": 173248,
    "rssi": -73, "type": "sgv", "glucose": 131
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:33:13.147Z", "sgv": 129,
    "device": "xdripjs://RigName", "filtered": 168064, "date": 1536078793147, "unfiltered": 170336,
    "rssi": -72, "type": "sgv", "glucose": 129
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:28:12.175Z", "sgv": 128,
    "device": "xdripjs://RigName", "filtered": 165408, "date": 1536078492175, "unfiltered": 169536,
    "rssi": -62, "type": "sgv", "glucose": 128
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:23:13.157Z", "sgv": 126,
    "device": "xdripjs://RigName", "filtered": 163040, "date": 1536078193157, "unfiltered": 167968,
    "rssi": -59, "type": "sgv", "glucose": 126
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:18:12.215Z", "sgv": 123,
    "device": "xdripjs://RigName", "filtered": 161472, "date": 1536077892215, "unfiltered": 164512,
    "rssi": -73, "type": "sgv", "glucose": 123
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:13:12.288Z", "sgv": 120,
    "device": "xdripjs://RigName", "filtered": 160320, "date": 1536077592288, "unfiltered": 161600,
    "rssi": -64, "type": "sgv", "glucose": 120
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:08:13.106Z", "sgv": 119,
    "device": "xdripjs://RigName", "filtered": 158976, "date": 1536077293106, "unfiltered": 160096,
    "rssi": -65, "type": "sgv", "glucose": 119
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:03:12.285Z", "sgv": 119,
    "device": "xdripjs://RigName", "filtered": 157536, "date": 1536076992285, "unfiltered": 160288,
    "rssi": -73, "type": "sgv", "glucose": 119
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:58:13.088Z", "sgv": 118,
    "device": "xdripjs://RigName", "filtered": 156512, "date": 1536076693088, "unfiltered": 158944,
    "rssi": -68, "type": "sgv", "glucose": 118
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:53:12.190Z", "sgv": 116,
    "device": "xdripjs://RigName", "filtered": 156192, "date": 1536076392190, "unfiltered": 157152,
    "rssi": -64, "type": "sgv", "glucose": 116
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:48:12.184Z", "sgv": 115,
    "device": "xdripjs://RigName", "filtered": 156096, "date": 1536076092184, "unfiltered": 155840,
    "rssi": -66, "type": "sgv", "glucose": 115
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:43:12.517Z", "sgv": 114,
    "device": "xdripjs://RigName", "filtered": 155904, "date": 1536075792517, "unfiltered": 155264,
    "rssi": -64, "type": "sgv", "glucose": 114
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:38:12.169Z", "sgv": 116,
    "device": "xdripjs://RigName", "filtered": 155712, "date": 1536075492169, "unfiltered": 157248,
    "rssi": -68, "type": "sgv", "glucose": 116
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:33:13.123Z", "sgv": 115,
    "device": "xdripjs://RigName", "filtered": 155744, "date": 1536075193123, "unfiltered": 156096,
    "rssi": -75, "type": "sgv", "glucose": 115
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:28:12.581Z", "sgv": 113,
    "device": "xdripjs://RigName", "filtered": 156416, "date": 1536074892581, "unfiltered": 154400,
    "rssi": -67, "type": "sgv", "glucose": 113
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:23:12.375Z", "sgv": 116,
    "device": "xdripjs://RigName", "filtered": 158784, "date": 1536074592375, "unfiltered": 156832,
    "rssi": -64, "type": "sgv", "glucose": 116
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:18:12.178Z", "sgv": 118,
    "device": "xdripjs://RigName", "filtered": 164736, "date": 1536074292178, "unfiltered": 159040,
    "rssi": -70, "type": "sgv", "glucose": 118
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:13:12.567Z", "sgv": 121,
    "device": "xdripjs://RigName", "filtered": 174688, "date": 1536073992567, "unfiltered": 162688,
    "rssi": -93, "type": "sgv", "glucose": 121
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:08:12.279Z", "sgv": 125,
    "device": "xdripjs://RigName", "filtered": 185248, "date": 1536073692279, "unfiltered": 166656,
    "rssi": -75, "type": "sgv", "glucose": 125
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:03:12.238Z", "sgv": 133,
    "device": "xdripjs://RigName", "filtered": 192192, "date": 1536073392238, "unfiltered": 174432,
    "rssi": -68, "type": "sgv", "glucose": 133
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:58:12.717Z", "sgv": 149,
    "device": "xdripjs://RigName", "filtered": 193088, "date": 1536073092717, "unfiltered": 190880,
    "rssi": -66, "type": "sgv", "glucose": 149
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:53:12.671Z", "sgv": 151,
    "device": "xdripjs://RigName", "filtered": 190144, "date": 1536072792671, "unfiltered": 192960,
    "rssi": -74, "type": "sgv", "glucose": 151
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:48:12.549Z", "sgv": 155,
    "device": "xdripjs://RigName", "filtered": 187584, "date": 1536072492549, "unfiltered": 196832,
    "rssi": -82, "type": "sgv", "glucose": 155
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:43:12.475Z", "sgv": 148,
    "device": "xdripjs://RigName", "filtered": 187264, "date": 1536072192475, "unfiltered": 189664,
    "rssi": -85, "type": "sgv", "glucose": 148
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:38:12.278Z", "sgv": 142,
    "device": "xdripjs://RigName", "filtered": 188768, "date": 1536071892278, "unfiltered": 184032,
    "rssi": -82, "type": "sgv", "glucose": 142
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:33:12.381Z", "sgv": 146,
    "device": "xdripjs://RigName", "filtered": 190336, "date": 1536071592381, "unfiltered": 187680,
    "rssi": -74, "type": "sgv", "glucose": 146
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:28:12.348Z", "sgv": 148,
    "device": "xdripjs://RigName", "filtered": 191424, "date": 1536071292348, "unfiltered": 190016,
    "rssi": -70, "type": "sgv", "glucose": 148
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:23:12.378Z", "sgv": 150,
    "device": "xdripjs://RigName", "filtered": 192704, "date": 1536070992378, "unfiltered": 191424,
    "rssi": -72, "type": "sgv", "glucose": 150
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:18:12.316Z", "sgv": 150,
    "device": "xdripjs://RigName", "filtered": 194432, "date": 1536070692316, "unfiltered": 191936,
    "rssi": -74, "type": "sgv", "glucose": 150
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:13:12.689Z", "sgv": 152,
    "device": "xdripjs://RigName", "filtered": 196416, "date": 1536070392689, "unfiltered": 193536,
    "rssi": -73, "type": "sgv", "glucose": 152
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:08:12.328Z", "sgv": 153,
    "device": "xdripjs://RigName", "filtered": 197920, "date": 1536070092328, "unfiltered": 195008,
    "rssi": -75, "type": "sgv", "glucose": 153
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:03:12.372Z", "sgv": 155,
    "device": "xdripjs://RigName", "filtered": 198240, "date": 1536069792372, "unfiltered": 196704,
    "rssi": -65, "type": "sgv", "glucose": 155
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T13:58:12.944Z", "sgv": 157,
    "device": "xdripjs://RigName", "filtered": 197088, "date": 1536069492944, "unfiltered": 198176,
    "rssi": -67, "type": "sgv", "glucose": 157
  }
]

EOT

    # Make a fake raw_glucose.json without calibrated glucose to test the raw command
    cat >raw_glucose.json <<EOT
[
  {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T14:58:09.623Z",
    "device": "xdripjs://RigName", "filtered": 168800, "date": 1536159489623, "unfiltered": 184416,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T14:53:09.786Z",
    "device": "xdripjs://RigName", "filtered": 153632, "date": 1536159189786, "unfiltered": 178496,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T14:48:09.731Z",
    "device": "xdripjs://RigName", "filtered": 141120, "date": 1536158889731, "unfiltered": 165536,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T14:43:09.747Z",
    "device": "xdripjs://RigName", "filtered": 134432, "date": 1536158589747, "unfiltered": 150048,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:38:10.581Z",
    "device": "xdripjs://RigName", "filtered": 133056, "date": 1536158290581, "unfiltered": 133728,
    "rssi": -60, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:23:09.777Z",
    "device": "xdripjs://RigName", "filtered": 138176, "date": 1536157389777, "unfiltered": 134592,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:18:09.822Z",
    "device": "xdripjs://RigName", "filtered": 140128, "date": 1536157089822, "unfiltered": 137376,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:13:09.824Z",
    "device": "xdripjs://RigName", "filtered": 141888, "date": 1536156789824, "unfiltered": 139520,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:08:09.829Z",
    "device": "xdripjs://RigName", "filtered": 143488, "date": 1536156489829, "unfiltered": 140416,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T14:03:09.858Z",
    "device": "xdripjs://RigName", "filtered": 144864, "date": 1536156189858, "unfiltered": 142784,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:58:10.019Z",
    "device": "xdripjs://RigName", "filtered": 146208, "date": 1536155890019, "unfiltered": 144416,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:53:10.088Z",
    "device": "xdripjs://RigName", "filtered": 147648, "date": 1536155590088, "unfiltered": 145984,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:48:09.748Z",
    "device": "xdripjs://RigName", "filtered": 149248, "date": 1536155289748, "unfiltered": 146144,
    "rssi": -75, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:43:10.020Z",
    "device": "xdripjs://RigName", "filtered": 150752, "date": 1536154990020, "unfiltered": 149024,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:38:10.121Z",
    "device": "xdripjs://RigName", "filtered": 151808, "date": 1536154690121, "unfiltered": 149440,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:28:10.277Z",
    "device": "xdripjs://RigName", "filtered": 152000, "date": 1536154090277, "unfiltered": 151808,
    "rssi": -60, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:23:10.502Z",
    "device": "xdripjs://RigName", "filtered": 151232, "date": 1536153790502, "unfiltered": 152832,
    "rssi": -80, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:18:09.814Z",
    "device": "xdripjs://RigName", "filtered": 149824, "date": 1536153489814, "unfiltered": 151776,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:13:09.799Z",
    "device": "xdripjs://RigName", "filtered": 147616, "date": 1536153189799, "unfiltered": 149920,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:08:09.901Z",
    "device": "xdripjs://RigName", "filtered": 144416, "date": 1536152889901, "unfiltered": 149344,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T13:03:09.901Z",
    "device": "xdripjs://RigName", "filtered": 140352, "date": 1536152589901, "unfiltered": 146144,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:58:09.936Z",
    "device": "xdripjs://RigName", "filtered": 136160, "date": 1536152289936, "unfiltered": 142656,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:53:10.044Z",
    "device": "xdripjs://RigName", "filtered": 132672, "date": 1536151990044, "unfiltered": 139520,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:48:09.862Z",
    "device": "xdripjs://RigName", "filtered": 130656, "date": 1536151689862, "unfiltered": 134080,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:43:09.861Z",
    "device": "xdripjs://RigName", "filtered": 130352, "date": 1536151389861, "unfiltered": 132192,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:38:09.979Z",
    "device": "xdripjs://RigName", "filtered": 131264, "date": 1536151089979, "unfiltered": 129952,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:33:10.038Z",
    "device": "xdripjs://RigName", "filtered": 132864, "date": 1536150790038, "unfiltered": 129792,
    "rssi": -78, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:28:09.991Z",
    "device": "xdripjs://RigName", "filtered": 134720, "date": 1536150489991, "unfiltered": 132320,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:23:10.111Z",
    "device": "xdripjs://RigName", "filtered": 136800, "date": 1536150190111, "unfiltered": 133952,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:18:10.020Z",
    "device": "xdripjs://RigName", "filtered": 138912, "date": 1536149890020, "unfiltered": 135488,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:13:10.039Z",
    "device": "xdripjs://RigName", "filtered": 140736, "date": 1536149590039, "unfiltered": 137376,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:08:10.426Z",
    "device": "xdripjs://RigName", "filtered": 142240, "date": 1536149290426, "unfiltered": 139808,
    "rssi": -71, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T12:03:10.079Z",
    "device": "xdripjs://RigName", "filtered": 143616, "date": 1536148990079, "unfiltered": 142208,
    "rssi": -71, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:58:10.242Z",
    "device": "xdripjs://RigName", "filtered": 145120, "date": 1536148690242, "unfiltered": 142752,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:53:10.255Z",
    "device": "xdripjs://RigName", "filtered": 146432, "date": 1536148390255, "unfiltered": 144128,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:48:09.968Z",
    "device": "xdripjs://RigName", "filtered": 147040, "date": 1536148089968, "unfiltered": 145568,
    "rssi": -85, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:43:09.969Z",
    "device": "xdripjs://RigName", "filtered": 146720, "date": 1536147789969, "unfiltered": 146592,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:38:09.562Z",
    "device": "xdripjs://RigName", "filtered": 145536, "date": 1536147489562, "unfiltered": 147296,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:28:10.085Z",
    "device": "xdripjs://RigName", "filtered": 141408, "date": 1536146890085, "unfiltered": 144672,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:23:10.839Z",
    "device": "xdripjs://RigName", "filtered": 138976, "date": 1536146590839, "unfiltered": 143040,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:18:11.253Z",
    "device": "xdripjs://RigName", "filtered": 136352, "date": 1536146291253, "unfiltered": 140160,
    "rssi": -87, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:13:11.320Z",
    "device": "xdripjs://RigName", "filtered": 133600, "date": 1536145991320, "unfiltered": 137600,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:08:11.297Z",
    "device": "xdripjs://RigName", "filtered": 130704, "date": 1536145691297, "unfiltered": 135584,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T11:03:11.327Z",
    "device": "xdripjs://RigName", "filtered": 127312, "date": 1536145391327, "unfiltered": 132000,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:58:11.318Z",
    "device": "xdripjs://RigName", "filtered": 123200, "date": 1536145091318, "unfiltered": 128544,
    "rssi": -81, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:53:11.283Z",
    "device": "xdripjs://RigName", "filtered": 118592, "date": 1536144791283, "unfiltered": 125808,
    "rssi": -71, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:48:11.181Z",
    "device": "xdripjs://RigName", "filtered": 113920, "date": 1536144491181, "unfiltered": 122160,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:43:11.297Z",
    "device": "xdripjs://RigName", "filtered": 109600, "date": 1536144191297, "unfiltered": 115712,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:38:11.116Z",
    "device": "xdripjs://RigName", "filtered": 105760, "date": 1536143891116, "unfiltered": 112048,
    "rssi": -69, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:33:11.211Z",
    "device": "xdripjs://RigName", "filtered": 102368, "date": 1536143591211, "unfiltered": 107984,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:28:11.364Z",
    "device": "xdripjs://RigName", "filtered": 99440, "date": 1536143291364, "unfiltered": 104128,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:23:11.353Z",
    "device": "xdripjs://RigName", "filtered": 96832, "date": 1536142991353, "unfiltered": 100528,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:18:11.230Z",
    "device": "xdripjs://RigName", "filtered": 94736, "date": 1536142691230, "unfiltered": 98288,
    "rssi": -75, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:13:10.540Z",
    "device": "xdripjs://RigName", "filtered": 93344, "date": 1536142390540, "unfiltered": 96560,
    "rssi": -69, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:08:11.212Z",
    "device": "xdripjs://RigName", "filtered": 92656, "date": 1536142091212, "unfiltered": 93616,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T10:03:11.347Z",
    "device": "xdripjs://RigName", "filtered": 92336, "date": 1536141791347, "unfiltered": 92496,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:58:11.231Z",
    "device": "xdripjs://RigName", "filtered": 92000, "date": 1536141491231, "unfiltered": 92672,
    "rssi": -89, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:53:11.299Z",
    "device": "xdripjs://RigName", "filtered": 91584, "date": 1536141191299, "unfiltered": 92048,
    "rssi": -84, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:48:11.391Z",
    "device": "xdripjs://RigName", "filtered": 91216, "date": 1536140891391, "unfiltered": 91968,
    "rssi": -88, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:43:11.504Z",
    "device": "xdripjs://RigName", "filtered": 90784, "date": 1536140591504, "unfiltered": 91664,
    "rssi": -85, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:38:11.679Z",
    "device": "xdripjs://RigName", "filtered": 89952, "date": 1536140291679, "unfiltered": 90640,
    "rssi": -92, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:33:11.262Z",
    "device": "xdripjs://RigName", "filtered": 88704, "date": 1536139991262, "unfiltered": 89792,
    "rssi": -86, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:28:11.439Z",
    "device": "xdripjs://RigName", "filtered": 87776, "date": 1536139691439, "unfiltered": 90224,
    "rssi": -90, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:23:10.725Z",
    "device": "xdripjs://RigName", "filtered": 88144, "date": 1536139390725, "unfiltered": 89520,
    "rssi": -86, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:13:10.924Z",
    "device": "xdripjs://RigName", "filtered": 92432, "date": 1536138790924, "unfiltered": 88160,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:08:11.372Z",
    "device": "xdripjs://RigName", "filtered": 94080, "date": 1536138491372, "unfiltered": 90176,
    "rssi": -78, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T09:03:11.511Z",
    "device": "xdripjs://RigName", "filtered": 95168, "date": 1536138191511, "unfiltered": 93200,
    "rssi": -78, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:58:11.357Z",
    "device": "xdripjs://RigName", "filtered": 96640, "date": 1536137891357, "unfiltered": 96624,
    "rssi": -78, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:53:11.464Z",
    "device": "xdripjs://RigName", "filtered": 99072, "date": 1536137591464, "unfiltered": 95840,
    "rssi": -78, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:48:11.320Z",
    "device": "xdripjs://RigName", "filtered": 101856, "date": 1536137291320, "unfiltered": 96560,
    "rssi": -85, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:43:11.359Z",
    "device": "xdripjs://RigName", "filtered": 104000, "date": 1536136991359, "unfiltered": 99648,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:38:10.748Z",
    "device": "xdripjs://RigName", "filtered": 105552, "date": 1536136690748, "unfiltered": 103424,
    "rssi": -95, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:33:10.839Z",
    "device": "xdripjs://RigName", "filtered": 107360, "date": 1536136390839, "unfiltered": 105696,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:28:11.487Z",
    "device": "xdripjs://RigName", "filtered": 109936, "date": 1536136091487, "unfiltered": 106592,
    "rssi": -78, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:23:11.156Z",
    "device": "xdripjs://RigName", "filtered": 112736, "date": 1536135791156, "unfiltered": 108096,
    "rssi": -95, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:18:11.285Z",
    "device": "xdripjs://RigName", "filtered": 115072, "date": 1536135491285, "unfiltered": 110016,
    "rssi": -98, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:13:10.975Z",
    "device": "xdripjs://RigName", "filtered": 116896, "date": 1536135190975, "unfiltered": 114544,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T08:08:10.733Z",
    "device": "xdripjs://RigName", "filtered": 118608, "date": 1536134890733, "unfiltered": 116928,
    "rssi": -69, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:53:10.547Z",
    "device": "xdripjs://RigName", "filtered": 126352, "date": 1536133990547, "unfiltered": 122864,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:48:10.633Z",
    "device": "xdripjs://RigName", "filtered": 129408, "date": 1536133690633, "unfiltered": 122928,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:43:10.464Z",
    "device": "xdripjs://RigName", "filtered": 132224, "date": 1536133390464, "unfiltered": 129216,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:38:10.477Z",
    "device": "xdripjs://RigName", "filtered": 134560, "date": 1536133090477, "unfiltered": 129952,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:33:10.581Z",
    "device": "xdripjs://RigName", "filtered": 136512, "date": 1536132790581, "unfiltered": 133568,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:28:10.505Z",
    "device": "xdripjs://RigName", "filtered": 138080, "date": 1536132490505, "unfiltered": 135488,
    "rssi": -56, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:23:10.519Z",
    "device": "xdripjs://RigName", "filtered": 139584, "date": 1536132190519, "unfiltered": 137824,
    "rssi": -50, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:18:10.472Z",
    "device": "xdripjs://RigName", "filtered": 141184, "date": 1536131890472, "unfiltered": 138560,
    "rssi": -50, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:13:10.606Z",
    "device": "xdripjs://RigName", "filtered": 142944, "date": 1536131590606, "unfiltered": 140448,
    "rssi": -55, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:08:10.637Z",
    "device": "xdripjs://RigName", "filtered": 144736, "date": 1536131290637, "unfiltered": 142016,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T07:03:10.549Z",
    "device": "xdripjs://RigName", "filtered": 146464, "date": 1536130990549, "unfiltered": 143520,
    "rssi": -49, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:58:10.848Z",
    "device": "xdripjs://RigName", "filtered": 148128, "date": 1536130690848, "unfiltered": 145760,
    "rssi": -56, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:53:10.609Z",
    "device": "xdripjs://RigName", "filtered": 149792, "date": 1536130390609, "unfiltered": 147424,
    "rssi": -53, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:48:11.252Z",
    "device": "xdripjs://RigName", "filtered": 151488, "date": 1536130091252, "unfiltered": 148864,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:43:10.667Z",
    "device": "xdripjs://RigName", "filtered": 153280, "date": 1536129790667, "unfiltered": 150496,
    "rssi": -55, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:38:10.877Z",
    "device": "xdripjs://RigName", "filtered": 155232, "date": 1536129490877, "unfiltered": 152512,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:33:10.592Z",
    "device": "xdripjs://RigName", "filtered": 157472, "date": 1536129190592, "unfiltered": 154272,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:28:10.501Z",
    "device": "xdripjs://RigName", "filtered": 160032, "date": 1536128890501, "unfiltered": 156416,
    "rssi": -50, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:23:10.560Z",
    "device": "xdripjs://RigName", "filtered": 162560, "date": 1536128590560, "unfiltered": 158496,
    "rssi": -50, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:18:11.011Z",
    "device": "xdripjs://RigName", "filtered": 164704, "date": 1536128291011, "unfiltered": 160672,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:13:11.025Z",
    "device": "xdripjs://RigName", "filtered": 166368, "date": 1536127991025, "unfiltered": 163904,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:08:10.753Z",
    "device": "xdripjs://RigName", "filtered": 167840, "date": 1536127690753, "unfiltered": 166016,
    "rssi": -60, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T06:03:10.572Z",
    "device": "xdripjs://RigName", "filtered": 169376, "date": 1536127390572, "unfiltered": 166976,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:58:10.631Z",
    "device": "xdripjs://RigName", "filtered": 171072, "date": 1536127090631, "unfiltered": 168512,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:53:10.690Z",
    "device": "xdripjs://RigName", "filtered": 172896, "date": 1536126790690, "unfiltered": 170368,
    "rssi": -53, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:48:11.064Z",
    "device": "xdripjs://RigName", "filtered": 174944, "date": 1536126491064, "unfiltered": 171904,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:43:10.792Z",
    "device": "xdripjs://RigName", "filtered": 177088, "date": 1536126190792, "unfiltered": 174016,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:38:10.790Z",
    "device": "xdripjs://RigName", "filtered": 179008, "date": 1536125890790, "unfiltered": 175488,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:33:10.999Z",
    "device": "xdripjs://RigName", "filtered": 180576, "date": 1536125590999, "unfiltered": 178048,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:28:10.699Z",
    "device": "xdripjs://RigName", "filtered": 181792, "date": 1536125290699, "unfiltered": 180032,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:23:10.935Z",
    "device": "xdripjs://RigName", "filtered": 183008, "date": 1536124990935, "unfiltered": 181184,
    "rssi": -53, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:18:10.814Z",
    "device": "xdripjs://RigName", "filtered": 184352, "date": 1536124690814, "unfiltered": 182880,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:13:10.767Z",
    "device": "xdripjs://RigName", "filtered": 185664, "date": 1536124390767, "unfiltered": 183328,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:08:10.782Z",
    "device": "xdripjs://RigName", "filtered": 186720, "date": 1536124090782, "unfiltered": 184512,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T05:03:10.854Z",
    "device": "xdripjs://RigName", "filtered": 187552, "date": 1536123790854, "unfiltered": 186592,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:58:10.778Z",
    "device": "xdripjs://RigName", "filtered": 188512, "date": 1536123490778, "unfiltered": 187200,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:53:10.793Z",
    "device": "xdripjs://RigName", "filtered": 190016, "date": 1536123190793, "unfiltered": 188576,
    "rssi": -51, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:48:10.792Z",
    "device": "xdripjs://RigName", "filtered": 191936, "date": 1536122890792, "unfiltered": 189056,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:43:10.716Z",
    "device": "xdripjs://RigName", "filtered": 193856, "date": 1536122590716, "unfiltered": 190240,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:38:10.970Z",
    "device": "xdripjs://RigName", "filtered": 195424, "date": 1536122290970, "unfiltered": 192832,
    "rssi": -59, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:33:11.224Z",
    "device": "xdripjs://RigName", "filtered": 196256, "date": 1536121991224, "unfiltered": 195360,
    "rssi": -58, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:28:10.745Z",
    "device": "xdripjs://RigName", "filtered": 196288, "date": 1536121690745, "unfiltered": 194720,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:23:10.880Z",
    "device": "xdripjs://RigName", "filtered": 195776, "date": 1536121390880, "unfiltered": 197088,
    "rssi": -91, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:18:10.865Z",
    "device": "xdripjs://RigName", "filtered": 195296, "date": 1536121090865, "unfiltered": 196576,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:13:11.119Z",
    "device": "xdripjs://RigName", "filtered": 195488, "date": 1536120791119, "unfiltered": 195968,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:08:10.803Z",
    "device": "xdripjs://RigName", "filtered": 196352, "date": 1536120490803, "unfiltered": 195040,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T04:03:11.269Z",
    "device": "xdripjs://RigName", "filtered": 197408, "date": 1536120191269, "unfiltered": 195648,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:58:11.192Z",
    "device": "xdripjs://RigName", "filtered": 198016, "date": 1536119891192, "unfiltered": 196608,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:53:10.909Z",
    "device": "xdripjs://RigName", "filtered": 197952, "date": 1536119590909, "unfiltered": 197536,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:48:11.011Z",
    "device": "xdripjs://RigName", "filtered": 197280, "date": 1536119291011, "unfiltered": 198432,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:43:11.038Z",
    "device": "xdripjs://RigName", "filtered": 195968, "date": 1536118991038, "unfiltered": 197952,
    "rssi": -58, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:38:10.939Z",
    "device": "xdripjs://RigName", "filtered": 193856, "date": 1536118690939, "unfiltered": 196256,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:33:10.884Z",
    "device": "xdripjs://RigName", "filtered": 190688, "date": 1536118390884, "unfiltered": 195136,
    "rssi": -69, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:28:12.033Z",
    "device": "xdripjs://RigName", "filtered": 186880, "date": 1536118092033, "unfiltered": 192224,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:23:12.090Z",
    "device": "xdripjs://RigName", "filtered": 183232, "date": 1536117792090, "unfiltered": 190368,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:18:12.359Z",
    "device": "xdripjs://RigName", "filtered": 180256, "date": 1536117492359, "unfiltered": 185120,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:13:12.087Z",
    "device": "xdripjs://RigName", "filtered": 178016, "date": 1536117192087, "unfiltered": 181280,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:08:12.073Z",
    "device": "xdripjs://RigName", "filtered": 175776, "date": 1536116892073, "unfiltered": 179456,
    "rssi": -58, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T03:03:12.283Z",
    "device": "xdripjs://RigName", "filtered": 173152, "date": 1536116592283, "unfiltered": 175872,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:58:11.992Z",
    "device": "xdripjs://RigName", "filtered": 170016, "date": 1536116291992, "unfiltered": 175360,
    "rssi": -59, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:53:12.142Z",
    "device": "xdripjs://RigName", "filtered": 166656, "date": 1536115992142, "unfiltered": 171776,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:48:12.022Z",
    "device": "xdripjs://RigName", "filtered": 163616, "date": 1536115692022, "unfiltered": 168672,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:43:11.927Z",
    "device": "xdripjs://RigName", "filtered": 160544, "date": 1536115391927, "unfiltered": 165824,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:38:12.227Z",
    "device": "xdripjs://RigName", "filtered": 157120, "date": 1536115092227, "unfiltered": 160480,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:33:12.030Z",
    "device": "xdripjs://RigName", "filtered": 153600, "date": 1536114792030, "unfiltered": 159744,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:28:12.254Z",
    "device": "xdripjs://RigName", "filtered": 150400, "date": 1536114492254, "unfiltered": 156736,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:23:11.981Z",
    "device": "xdripjs://RigName", "filtered": 147744, "date": 1536114191981, "unfiltered": 151488,
    "rssi": -60, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:18:12.071Z",
    "device": "xdripjs://RigName", "filtered": 145024, "date": 1536113892071, "unfiltered": 148544,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:13:12.085Z",
    "device": "xdripjs://RigName", "filtered": 142496, "date": 1536113592085, "unfiltered": 145664,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:08:12.263Z",
    "device": "xdripjs://RigName", "filtered": 142048, "date": 1536113292263, "unfiltered": 145728,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T02:03:12.202Z",
    "device": "xdripjs://RigName", "filtered": 145696, "date": 1536112992202, "unfiltered": 144000,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:58:11.592Z",
    "device": "xdripjs://RigName", "filtered": 153632, "date": 1536112691592, "unfiltered": 142784,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "SingleDown", "noise": 1, "dateString": "2018-09-05T01:53:11.560Z",
    "device": "xdripjs://RigName", "filtered": 164032, "date": 1536112391560, "unfiltered": 146912,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:48:12.182Z",
    "device": "xdripjs://RigName", "filtered": 174240, "date": 1536112092182, "unfiltered": 157952,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:43:12.060Z",
    "device": "xdripjs://RigName", "filtered": 183072, "date": 1536111792060, "unfiltered": 167456,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-05T01:38:12.059Z",
    "device": "xdripjs://RigName", "filtered": 190400, "date": 1536111492059, "unfiltered": 180224,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:33:12.042Z",
    "device": "xdripjs://RigName", "filtered": 196000, "date": 1536111192042, "unfiltered": 186784,
    "rssi": -71, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:28:12.175Z",
    "device": "xdripjs://RigName", "filtered": 199616, "date": 1536110892175, "unfiltered": 191712,
    "rssi": -85, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:23:12.144Z",
    "device": "xdripjs://RigName", "filtered": 200896, "date": 1536110592144, "unfiltered": 198528,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:18:12.308Z",
    "device": "xdripjs://RigName", "filtered": 199968, "date": 1536110292308, "unfiltered": 201216,
    "rssi": -80, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T01:13:11.774Z",
    "device": "xdripjs://RigName", "filtered": 196384, "date": 1536109991774, "unfiltered": 201120,
    "rssi": -60, "type": "sgv"
  }, {
    "direction": "FortyFiveUp", "noise": 1, "dateString": "2018-09-05T01:08:12.100Z",
    "device": "xdripjs://RigName", "filtered": 189152, "date": 1536109692100, "unfiltered": 196224,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T01:03:11.375Z",
    "device": "xdripjs://RigName", "filtered": 177856, "date": 1536109391375, "unfiltered": 194080,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "SingleUp", "noise": 1, "dateString": "2018-09-05T00:58:11.403Z",
    "device": "xdripjs://RigName", "filtered": 162752, "date": 1536109091403, "unfiltered": 185920,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T00:53:11.449Z",
    "device": "xdripjs://RigName", "filtered": 144448, "date": 1536108791449, "unfiltered": 170400,
    "rssi": -74, "type": "sgv"
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T00:48:11.417Z",
    "device": "xdripjs://RigName", "filtered": 124656, "date": 1536108491417, "unfiltered": 153120,
    "rssi": -69, "type": "sgv"
  }, {
    "direction": "DoubleUp", "noise": 1, "dateString": "2018-09-05T00:43:11.384Z",
    "device": "xdripjs://RigName", "filtered": 107120, "date": 1536108191384, "unfiltered": 138976,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "FortyFiveUp", "noise": 1, "dateString": "2018-09-05T00:38:11.985Z",
    "device": "xdripjs://RigName", "filtered": 95520, "date": 1536107891985, "unfiltered": 119904,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:33:12.181Z",
    "device": "xdripjs://RigName", "filtered": 90672, "date": 1536107592181, "unfiltered": 99104,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:28:11.742Z",
    "device": "xdripjs://RigName", "filtered": 90400, "date": 1536107291742, "unfiltered": 89728,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:23:11.454Z",
    "device": "xdripjs://RigName", "filtered": 92208, "date": 1536106991454, "unfiltered": 90352,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:18:11.331Z",
    "device": "xdripjs://RigName", "filtered": 95248, "date": 1536106691331, "unfiltered": 90992,
    "rssi": -71, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:13:11.389Z",
    "device": "xdripjs://RigName", "filtered": 99440, "date": 1536106391389, "unfiltered": 93264,
    "rssi": -59, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:08:11.701Z",
    "device": "xdripjs://RigName", "filtered": 104176, "date": 1536106091701, "unfiltered": 97680,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-05T00:03:12.207Z",
    "device": "xdripjs://RigName", "filtered": 108672, "date": 1536105792207, "unfiltered": 100336,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:58:11.352Z",
    "device": "xdripjs://RigName", "filtered": 111984, "date": 1536105491352, "unfiltered": 106400,
    "rssi": -75, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:53:11.659Z",
    "device": "xdripjs://RigName", "filtered": 113744, "date": 1536105191659, "unfiltered": 109840,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:48:11.323Z",
    "device": "xdripjs://RigName", "filtered": 114528, "date": 1536104891323, "unfiltered": 113648,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:43:11.446Z",
    "device": "xdripjs://RigName", "filtered": 114944, "date": 1536104591446, "unfiltered": 115008,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:38:11.473Z",
    "device": "xdripjs://RigName", "filtered": 115520, "date": 1536104291473, "unfiltered": 114272,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:33:11.363Z",
    "device": "xdripjs://RigName", "filtered": 116528, "date": 1536103991363, "unfiltered": 115376,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:28:11.370Z",
    "device": "xdripjs://RigName", "filtered": 118288, "date": 1536103691370, "unfiltered": 116176,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:23:11.380Z",
    "device": "xdripjs://RigName", "filtered": 121648, "date": 1536103391380, "unfiltered": 117344,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T23:18:11.383Z",
    "device": "xdripjs://RigName", "filtered": 127376, "date": 1536103091383, "unfiltered": 120448,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T23:13:11.327Z",
    "device": "xdripjs://RigName", "filtered": 135008, "date": 1536102791327, "unfiltered": 124880,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T23:08:11.409Z",
    "device": "xdripjs://RigName", "filtered": 142464, "date": 1536102491409, "unfiltered": 128784,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T23:03:11.428Z",
    "device": "xdripjs://RigName", "filtered": 147328, "date": 1536102191428, "unfiltered": 136288,
    "rssi": -69, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:58:11.490Z",
    "device": "xdripjs://RigName", "filtered": 148896, "date": 1536101891490, "unfiltered": 145920,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:53:11.708Z",
    "device": "xdripjs://RigName", "filtered": 148576, "date": 1536101591708, "unfiltered": 149824,
    "rssi": -75, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:48:11.420Z",
    "device": "xdripjs://RigName", "filtered": 148320, "date": 1536101291420, "unfiltered": 149664,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:43:11.464Z",
    "device": "xdripjs://RigName", "filtered": 148960, "date": 1536100991464, "unfiltered": 148768,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:38:11.520Z",
    "device": "xdripjs://RigName", "filtered": 150432, "date": 1536100691520, "unfiltered": 148128,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:33:11.790Z",
    "device": "xdripjs://RigName", "filtered": 152288, "date": 1536100391790, "unfiltered": 149184,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:28:11.471Z",
    "device": "xdripjs://RigName", "filtered": 154432, "date": 1536100091471, "unfiltered": 151168,
    "rssi": -63, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:23:11.936Z",
    "device": "xdripjs://RigName", "filtered": 157600, "date": 1536099791936, "unfiltered": 153696,
    "rssi": -88, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T22:18:11.528Z",
    "device": "xdripjs://RigName", "filtered": 162496, "date": 1536099491528, "unfiltered": 156896,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T22:13:11.601Z",
    "device": "xdripjs://RigName", "filtered": 169344, "date": 1536099191601, "unfiltered": 159136,
    "rssi": -59, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T22:08:11.764Z",
    "device": "xdripjs://RigName", "filtered": 177248, "date": 1536098891764, "unfiltered": 165600,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T22:03:11.642Z",
    "device": "xdripjs://RigName", "filtered": 184608, "date": 1536098591642, "unfiltered": 171712,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T21:58:11.655Z",
    "device": "xdripjs://RigName", "filtered": 190368, "date": 1536098291655, "unfiltered": 180096,
    "rssi": -69, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:53:11.459Z",
    "device": "xdripjs://RigName", "filtered": 193984, "date": 1536097991459, "unfiltered": 188384,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:48:11.787Z",
    "device": "xdripjs://RigName", "filtered": 196224, "date": 1536097691787, "unfiltered": 191328,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:43:11.575Z",
    "device": "xdripjs://RigName", "filtered": 198592, "date": 1536097391575, "unfiltered": 196832,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:38:11.651Z",
    "device": "xdripjs://RigName", "filtered": 202432, "date": 1536097091651, "unfiltered": 198464,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:33:11.500Z",
    "device": "xdripjs://RigName", "filtered": 208032, "date": 1536096791500, "unfiltered": 199936,
    "rssi": -58, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T21:28:11.510Z",
    "device": "xdripjs://RigName", "filtered": 214336, "date": 1536096491510, "unfiltered": 203648,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:23:11.882Z",
    "device": "xdripjs://RigName", "filtered": 219456, "date": 1536096191882, "unfiltered": 211264,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:18:11.618Z",
    "device": "xdripjs://RigName", "filtered": 222368, "date": 1536095891618, "unfiltered": 214720,
    "rssi": -58, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:13:11.822Z",
    "device": "xdripjs://RigName", "filtered": 224288, "date": 1536095591822, "unfiltered": 221792,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T21:08:11.851Z",
    "device": "xdripjs://RigName", "filtered": 227200, "date": 1536095291851, "unfiltered": 227168,
    "rssi": -55, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 4, "dateString": "2018-09-04T21:03:12.298Z",
    "device": "xdripjs://RigName", "filtered": 232288, "date": 1536094992298, "unfiltered": 224512,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:28:11.686Z",
    "device": "xdripjs://RigName", "filtered": 260704, "date": 1536092891686, "unfiltered": 259936,
    "rssi": -44, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:23:11.985Z",
    "device": "xdripjs://RigName", "filtered": 261504, "date": 1536092591985, "unfiltered": 258080,
    "rssi": -48, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:18:11.642Z",
    "device": "xdripjs://RigName", "filtered": 260960, "date": 1536092291642, "unfiltered": 260992,
    "rssi": -59, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:13:11.834Z",
    "device": "xdripjs://RigName", "filtered": 259648, "date": 1536091991834, "unfiltered": 261504,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:08:11.774Z",
    "device": "xdripjs://RigName", "filtered": 259456, "date": 1536091691774, "unfiltered": 262272,
    "rssi": -53, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T20:03:11.758Z",
    "device": "xdripjs://RigName", "filtered": 261088, "date": 1536091391758, "unfiltered": 260864,
    "rssi": -74, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:58:11.714Z",
    "device": "xdripjs://RigName", "filtered": 263680, "date": 1536091091714, "unfiltered": 257440,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:53:12.100Z",
    "device": "xdripjs://RigName", "filtered": 266048, "date": 1536090792100, "unfiltered": 261504,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:48:11.859Z",
    "device": "xdripjs://RigName", "filtered": 267520, "date": 1536090491859, "unfiltered": 266176,
    "rssi": -53, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:43:11.739Z",
    "device": "xdripjs://RigName", "filtered": 268416, "date": 1536090191739, "unfiltered": 267008,
    "rssi": -57, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:38:11.872Z",
    "device": "xdripjs://RigName", "filtered": 268416, "date": 1536089891872, "unfiltered": 267200,
    "rssi": -58, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:33:12.502Z",
    "device": "xdripjs://RigName", "filtered": 267584, "date": 1536089592502, "unfiltered": 268288,
    "rssi": -79, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:28:12.875Z",
    "device": "xdripjs://RigName", "filtered": 266624, "date": 1536089292875, "unfiltered": 269248,
    "rssi": -77, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:23:12.748Z",
    "device": "xdripjs://RigName", "filtered": 266432, "date": 1536088992748, "unfiltered": 267968,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:18:12.777Z",
    "device": "xdripjs://RigName", "filtered": 266688, "date": 1536088692777, "unfiltered": 265984,
    "rssi": -52, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:13:12.810Z",
    "device": "xdripjs://RigName", "filtered": 266880, "date": 1536088392810, "unfiltered": 265216,
    "rssi": -58, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:08:12.864Z",
    "device": "xdripjs://RigName", "filtered": 266624, "date": 1536088092864, "unfiltered": 267648,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T19:03:13.028Z",
    "device": "xdripjs://RigName", "filtered": 266048, "date": 1536087793028, "unfiltered": 267520,
    "rssi": -48, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:58:12.876Z",
    "device": "xdripjs://RigName", "filtered": 265280, "date": 1536087492876, "unfiltered": 265600,
    "rssi": -50, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:53:12.769Z",
    "device": "xdripjs://RigName", "filtered": 264256, "date": 1536087192769, "unfiltered": 265984,
    "rssi": -48, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:48:12.917Z",
    "device": "xdripjs://RigName", "filtered": 262720, "date": 1536086892917, "unfiltered": 265472,
    "rssi": -47, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:43:12.796Z",
    "device": "xdripjs://RigName", "filtered": 260160, "date": 1536086592796, "unfiltered": 262912,
    "rssi": -49, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:38:12.988Z",
    "device": "xdripjs://RigName", "filtered": 256288, "date": 1536086292988, "unfiltered": 260864,
    "rssi": -49, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:33:13.041Z",
    "device": "xdripjs://RigName", "filtered": 251584, "date": 1536085993041, "unfiltered": 259520,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:28:13.105Z",
    "device": "xdripjs://RigName", "filtered": 246880, "date": 1536085693105, "unfiltered": 255360,
    "rssi": -80, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:23:12.936Z",
    "device": "xdripjs://RigName", "filtered": 242560, "date": 1536085392936, "unfiltered": 248608,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:18:12.919Z",
    "device": "xdripjs://RigName", "filtered": 238496, "date": 1536085092919, "unfiltered": 244384,
    "rssi": -50, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:13:13.117Z",
    "device": "xdripjs://RigName", "filtered": 234720, "date": 1536084793117, "unfiltered": 241344,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:08:12.990Z",
    "device": "xdripjs://RigName", "filtered": 231232, "date": 1536084492990, "unfiltered": 236992,
    "rssi": -53, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T18:03:12.838Z",
    "device": "xdripjs://RigName", "filtered": 227680, "date": 1536084192838, "unfiltered": 232448,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:58:13.094Z",
    "device": "xdripjs://RigName", "filtered": 223840, "date": 1536083893094, "unfiltered": 228896,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:53:13.029Z",
    "device": "xdripjs://RigName", "filtered": 219616, "date": 1536083593029, "unfiltered": 227424,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:48:12.256Z",
    "device": "xdripjs://RigName", "filtered": 215008, "date": 1536083292256, "unfiltered": 221024,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:43:13.039Z",
    "device": "xdripjs://RigName", "filtered": 209920, "date": 1536082993039, "unfiltered": 217408,
    "rssi": -60, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:38:12.517Z",
    "device": "xdripjs://RigName", "filtered": 204320, "date": 1536082692517, "unfiltered": 212992,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:33:13.110Z",
    "device": "xdripjs://RigName", "filtered": 198944, "date": 1536082393110, "unfiltered": 207552,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:28:13.003Z",
    "device": "xdripjs://RigName", "filtered": 194624, "date": 1536082093003, "unfiltered": 202240,
    "rssi": -61, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:23:12.286Z",
    "device": "xdripjs://RigName", "filtered": 191552, "date": 1536081792286, "unfiltered": 197728,
    "rssi": -55, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:18:12.226Z",
    "device": "xdripjs://RigName", "filtered": 189312, "date": 1536081492226, "unfiltered": 191648,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:13:12.596Z",
    "device": "xdripjs://RigName", "filtered": 187136, "date": 1536081192596, "unfiltered": 190304,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:08:12.934Z",
    "device": "xdripjs://RigName", "filtered": 184768, "date": 1536080892934, "unfiltered": 188480,
    "rssi": -54, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T17:03:12.947Z",
    "device": "xdripjs://RigName", "filtered": 182432, "date": 1536080592947, "unfiltered": 186560,
    "rssi": -49, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:58:12.991Z",
    "device": "xdripjs://RigName", "filtered": 179968, "date": 1536080292991, "unfiltered": 183520,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:53:13.079Z",
    "device": "xdripjs://RigName", "filtered": 177280, "date": 1536079993079, "unfiltered": 180608,
    "rssi": -56, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:48:13.092Z",
    "device": "xdripjs://RigName", "filtered": 174592, "date": 1536079693092, "unfiltered": 179360,
    "rssi": -76, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:43:13.045Z",
    "device": "xdripjs://RigName", "filtered": 172352, "date": 1536079393045, "unfiltered": 176736,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:38:12.329Z",
    "device": "xdripjs://RigName", "filtered": 170368, "date": 1536079092329, "unfiltered": 173248,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:33:13.147Z",
    "device": "xdripjs://RigName", "filtered": 168064, "date": 1536078793147, "unfiltered": 170336,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:28:12.175Z",
    "device": "xdripjs://RigName", "filtered": 165408, "date": 1536078492175, "unfiltered": 169536,
    "rssi": -62, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:23:13.157Z",
    "device": "xdripjs://RigName", "filtered": 163040, "date": 1536078193157, "unfiltered": 167968,
    "rssi": -59, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:18:12.215Z",
    "device": "xdripjs://RigName", "filtered": 161472, "date": 1536077892215, "unfiltered": 164512,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:13:12.288Z",
    "device": "xdripjs://RigName", "filtered": 160320, "date": 1536077592288, "unfiltered": 161600,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:08:13.106Z",
    "device": "xdripjs://RigName", "filtered": 158976, "date": 1536077293106, "unfiltered": 160096,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T16:03:12.285Z",
    "device": "xdripjs://RigName", "filtered": 157536, "date": 1536076992285, "unfiltered": 160288,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:58:13.088Z",
    "device": "xdripjs://RigName", "filtered": 156512, "date": 1536076693088, "unfiltered": 158944,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:53:12.190Z",
    "device": "xdripjs://RigName", "filtered": 156192, "date": 1536076392190, "unfiltered": 157152,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:48:12.184Z",
    "device": "xdripjs://RigName", "filtered": 156096, "date": 1536076092184, "unfiltered": 155840,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:43:12.517Z",
    "device": "xdripjs://RigName", "filtered": 155904, "date": 1536075792517, "unfiltered": 155264,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:38:12.169Z",
    "device": "xdripjs://RigName", "filtered": 155712, "date": 1536075492169, "unfiltered": 157248,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:33:13.123Z",
    "device": "xdripjs://RigName", "filtered": 155744, "date": 1536075193123, "unfiltered": 156096,
    "rssi": -75, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:28:12.581Z",
    "device": "xdripjs://RigName", "filtered": 156416, "date": 1536074892581, "unfiltered": 154400,
    "rssi": -67, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T15:23:12.375Z",
    "device": "xdripjs://RigName", "filtered": 158784, "date": 1536074592375, "unfiltered": 156832,
    "rssi": -64, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:18:12.178Z",
    "device": "xdripjs://RigName", "filtered": 164736, "date": 1536074292178, "unfiltered": 159040,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:13:12.567Z",
    "device": "xdripjs://RigName", "filtered": 174688, "date": 1536073992567, "unfiltered": 162688,
    "rssi": -93, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:08:12.279Z",
    "device": "xdripjs://RigName", "filtered": 185248, "date": 1536073692279, "unfiltered": 166656,
    "rssi": -75, "type": "sgv"
  }, {
    "direction": "FortyFiveDown", "noise": 1, "dateString": "2018-09-04T15:03:12.238Z",
    "device": "xdripjs://RigName", "filtered": 192192, "date": 1536073392238, "unfiltered": 174432,
    "rssi": -68, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:58:12.717Z",
    "device": "xdripjs://RigName", "filtered": 193088, "date": 1536073092717, "unfiltered": 190880,
    "rssi": -66, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:53:12.671Z",
    "device": "xdripjs://RigName", "filtered": 190144, "date": 1536072792671, "unfiltered": 192960,
    "rssi": -74, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:48:12.549Z",
    "device": "xdripjs://RigName", "filtered": 187584, "date": 1536072492549, "unfiltered": 196832,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:43:12.475Z",
    "device": "xdripjs://RigName", "filtered": 187264, "date": 1536072192475, "unfiltered": 189664,
    "rssi": -85, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:38:12.278Z",
    "device": "xdripjs://RigName", "filtered": 188768, "date": 1536071892278, "unfiltered": 184032,
    "rssi": -82, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:33:12.381Z",
    "device": "xdripjs://RigName", "filtered": 190336, "date": 1536071592381, "unfiltered": 187680,
    "rssi": -74, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:28:12.348Z",
    "device": "xdripjs://RigName", "filtered": 191424, "date": 1536071292348, "unfiltered": 190016,
    "rssi": -70, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:23:12.378Z",
    "device": "xdripjs://RigName", "filtered": 192704, "date": 1536070992378, "unfiltered": 191424,
    "rssi": -72, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:18:12.316Z",
    "device": "xdripjs://RigName", "filtered": 194432, "date": 1536070692316, "unfiltered": 191936,
    "rssi": -74, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:13:12.689Z",
    "device": "xdripjs://RigName", "filtered": 196416, "date": 1536070392689, "unfiltered": 193536,
    "rssi": -73, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:08:12.328Z",
    "device": "xdripjs://RigName", "filtered": 197920, "date": 1536070092328, "unfiltered": 195008,
    "rssi": -75, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T14:03:12.372Z",
    "device": "xdripjs://RigName", "filtered": 198240, "date": 1536069792372, "unfiltered": 196704,
    "rssi": -65, "type": "sgv"
  }, {
    "direction": "Flat", "noise": 1, "dateString": "2018-09-04T13:58:12.944Z",
    "device": "xdripjs://RigName", "filtered": 197088, "date": 1536069492944, "unfiltered": 198176,
    "rssi": -67, "type": "sgv"
  }
]

EOT
    # Make a fake lastreservoir.json to test the commands that extract values from it
    cat >lastreservoir.json <<EOT
50.75
EOT

    # Make a fake last_temp_basal to test the commands that extract values from it
    cat >last_temp_basal.json <<EOT
{
  "duration": 25,
  "temp": "absolute",
  "rate": 0
}
EOT

    # Make a fake temp_basal.json to test the commands that extract values from it
    cat >temp_basal.json <<EOT
{
  "duration": 13,
  "temp": "absolute",
  "rate": 1.4
}
EOT

    # Make a fake medtronic_frequency.ini to test the commands that extract values from it
    cat >medtronic_frequency.ini <<EOT
916650000
EOT

    # Make a fake mmtune.json to test the commands that extract values from it
    cat >mmtune.json <<EOT
{
  "scanDetails": [
    [ "916.300", 0, -128 ],
    [ "916.350", 0, -128 ],
    [ "916.400", 0, -128 ],
    [ "916.450", 0, -128 ],
    [ "916.500", 0, -128 ],
    [ "916.550", 0, -128 ],
    [ "916.600", 0, -83 ],
    [ "916.650", 0, -128 ],
    [ "916.700", 0, -128 ],
    [ "916.750", 0, -128 ],
    [ "916.800", 0, -128 ],
    [ "916.850", 0, -128 ],
    [ "916.900", 0, -128 ]
  ],
  "setFreq": 916.6,
  "usedDefault": true
}
EOT

    # Make a fake pumphistory_zoned.json to test the commands that extract values from it
    cat >pumphistory_zoned.json <<EOT
[
  {
    "timestamp": "2018-09-05T10:24:59-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T10:24:59-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.4
  }, {
    "timestamp": "2018-09-05T10:09:55-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T10:09:55-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T09:59:32-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T09:59:32-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.3
  }, {
    "timestamp": "2018-09-05T09:54:59-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.975, "duration": 0
  }, {
    "timestamp": "2018-09-05T09:54:33-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T09:54:33-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.15
  }, {
    "timestamp": "2018-09-05T09:50:34-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 0.8, "duration": 0
  }, {
    "timestamp": "2018-09-05T09:50:10-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T09:50:10-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.125
  }, {
    "timestamp": "2018-09-05T09:44:42-05:00", "_type": "Bolus", "amount": 0.6, "programmed": 0.6, "unabsorbed": 0.2, "duration": 0
  }, {
    "timestamp": "2018-09-05T09:44:23-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T09:44:23-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.8
  }, {
    "timestamp": "2018-09-05T09:39:39-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T09:39:39-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-05T09:04:33-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T09:04:33-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.9
  }, {
    "timestamp": "2018-09-05T08:39:41-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T08:39:41-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.25
  }, {
    "timestamp": "2018-09-05T08:34:18-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T08:34:18-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.025
  }, {
    "timestamp": "2018-09-05T08:32:18-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T08:32:18-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.125
  }, {
    "timestamp": "2018-09-05T07:55:02-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.225, "duration": 0
  }, {
    "timestamp": "2018-09-05T07:54:39-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T07:54:39-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.7
  }, {
    "timestamp": "2018-09-05T07:49:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T07:49:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.4
  }, {
    "timestamp": "2018-09-05T07:40:15-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T07:40:15-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.15
  }, {
    "timestamp": "2018-09-05T07:29:50-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T07:29:50-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-05T07:24:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T07:24:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.7
  }, {
    "timestamp": "2018-09-05T07:19:41-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T07:19:41-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1
  }, {
    "timestamp": "2018-09-05T06:59:24-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T06:59:24-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.3
  }, {
    "timestamp": "2018-09-05T06:54:56-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T06:54:56-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.45
  }, {
    "timestamp": "2018-09-05T06:42:29-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T06:42:29-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.7
  }, {
    "timestamp": "2018-09-05T06:39:47-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T06:39:47-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.05
  }, {
    "timestamp": "2018-09-05T06:25:14-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T06:25:14-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.8
  }, {
    "timestamp": "2018-09-05T06:22:25-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T06:22:25-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.6
  }, {
    "timestamp": "2018-09-05T06:19:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T06:19:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.8
  }, {
    "timestamp": "2018-09-05T06:05:06-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.2, "duration": 0
  }, {
    "timestamp": "2018-09-05T05:53:51-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.1, "duration": 0
  }, {
    "timestamp": "2018-09-05T05:50:06-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0, "duration": 0
  }, {
    "timestamp": "2018-09-05T05:49:41-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T05:49:41-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.15
  }, {
    "timestamp": "2018-09-05T05:34:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T05:34:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.75
  }, {
    "timestamp": "2018-09-05T05:29:31-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T05:29:31-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.6
  }, {
    "timestamp": "2018-09-05T05:07:46-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T05:07:46-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T04:52:32-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T04:52:32-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T04:52:30-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T04:52:30-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T04:34:56-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T04:34:56-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T04:21:24-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T04:21:24-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T03:44:43-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T03:44:43-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T03:29:47-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T03:29:47-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T03:14:21-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T03:14:21-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T03:10:30-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T03:10:30-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T02:54:45-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T02:54:45-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.1
  }, {
    "timestamp": "2018-09-05T02:49:42-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-05T02:49:42-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T02:34:58-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T02:34:58-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.2
  }, {
    "timestamp": "2018-09-05T02:24:58-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T02:24:58-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.3
  }, {
    "timestamp": "2018-09-05T02:14:58-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T02:14:58-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.5
  }, {
    "timestamp": "2018-09-05T01:44:52-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T01:44:52-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.45
  }, {
    "timestamp": "2018-09-05T01:22:38-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T01:22:38-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.6
  }, {
    "timestamp": "2018-09-05T01:19:43-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T01:19:43-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.05
  }, {
    "timestamp": "2018-09-05T01:04:53-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T01:04:53-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.65
  }, {
    "timestamp": "2018-09-05T00:59:30-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:59:30-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-05T00:54:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:54:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.75
  }, {
    "timestamp": "2018-09-05T00:34:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:34:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.55
  }, {
    "timestamp": "2018-09-05T00:29:56-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:29:56-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.85
  }, {
    "timestamp": "2018-09-05T00:24:33-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:24:33-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.4
  }, {
    "timestamp": "2018-09-05T00:19:39-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:19:39-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1
  }, {
    "timestamp": "2018-09-05T00:07:25-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:07:25-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.85
  }, {
    "timestamp": "2018-09-05T00:04:51-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-05T00:04:51-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.7
  }, {
    "timestamp": "2018-09-04T23:39:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T23:39:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T23:34:46-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T23:34:46-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.2
  }, {
    "timestamp": "2018-09-04T23:25:13-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T23:25:13-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.95
  }, {
    "timestamp": "2018-09-04T23:17:23-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T23:17:23-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.2
  }, {
    "timestamp": "2018-09-04T23:15:24-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.375, "duration": 0
  }, {
    "timestamp": "2018-09-04T23:14:59-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T23:14:59-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.65
  }, {
    "timestamp": "2018-09-04T22:59:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:59:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.95
  }, {
    "timestamp": "2018-09-04T22:50:13-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:50:13-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.25
  }, {
    "timestamp": "2018-09-04T22:45:05-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:45:05-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T22:35:05-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.65, "duration": 0
  }, {
    "timestamp": "2018-09-04T22:34:40-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:34:40-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T22:29:34-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:29:34-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.5
  }, {
    "timestamp": "2018-09-04T22:24:55-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 2.55, "duration": 0
  }, {
    "timestamp": "2018-09-04T22:24:34-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:24:34-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T22:20:29-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.475, "duration": 0
  }, {
    "timestamp": "2018-09-04T22:20:03-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:20:03-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T22:15:07-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.4, "duration": 0
  }, {
    "timestamp": "2018-09-04T22:14:44-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:14:44-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T22:10:04-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.35, "duration": 0
  }, {
    "timestamp": "2018-09-04T22:04:52-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.275, "duration": 0
  }, {
    "timestamp": "2018-09-04T22:04:34-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T22:04:34-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T22:00:22-05:00", "_type": "Bolus", "amount": 0.3, "programmed": 0.3, "unabsorbed": 2, "duration": 0
  }, {
    "timestamp": "2018-09-04T21:59:59-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:59:59-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.95
  }, {
    "timestamp": "2018-09-04T21:54:50-05:00", "_type": "Bolus", "amount": 0.4, "programmed": 0.4, "unabsorbed": 1.65, "duration": 0
  }, {
    "timestamp": "2018-09-04T21:54:29-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:54:29-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.375
  }, {
    "timestamp": "2018-09-04T21:49:47-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:49:47-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.45
  }, {
    "timestamp": "2018-09-04T21:45:52-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 1.5, "duration": 0
  }, {
    "timestamp": "2018-09-04T21:44:28-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:44:28-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.1
  }, {
    "timestamp": "2018-09-04T21:39:58-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:39:58-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.2
  }, {
    "timestamp": "2018-09-04T21:34:58-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1.45, "duration": 0
  }, {
    "timestamp": "2018-09-04T21:30:02-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1.375, "duration": 0
  }, {
    "timestamp": "2018-09-04T21:29:42-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:29:42-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.65
  }, {
    "timestamp": "2018-09-04T21:19:42-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:19:42-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.2
  }, {
    "timestamp": "2018-09-04T21:14:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:14:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.075
  }, {
    "timestamp": "2018-09-04T21:12:40-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:12:40-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T21:09:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T21:09:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.1
  }, {
    "timestamp": "2018-09-04T20:45:00-05:00", "_type": "TempBasalDuration", "duration (min)": 60
  }, {
    "timestamp": "2018-09-04T20:45:00-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T20:39:46-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:39:46-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T20:24:41-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:24:41-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T20:19:41-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:19:41-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T20:15:02-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:15:02-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.5
  }, {
    "timestamp": "2018-09-04T20:10:11-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1.7, "duration": 0
  }, {
    "timestamp": "2018-09-04T20:09:53-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:09:53-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.4
  }, {
    "timestamp": "2018-09-04T20:05:48-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 1.5, "duration": 0
  }, {
    "timestamp": "2018-09-04T20:05:24-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:05:24-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.125
  }, {
    "timestamp": "2018-09-04T20:03:38-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:03:38-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.1
  }, {
    "timestamp": "2018-09-04T20:02:11-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:02:11-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.025
  }, {
    "timestamp": "2018-09-04T20:00:34-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T20:00:34-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.1
  }, {
    "timestamp": "2018-09-04T19:59:42-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T19:59:42-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.2
  }, {
    "timestamp": "2018-09-04T19:55:26-05:00", "_type": "Bolus", "amount": 0.3, "programmed": 0.3, "unabsorbed": 1.25, "duration": 0
  }, {
    "timestamp": "2018-09-04T19:51:39-05:00", "_type": "Bolus", "amount": 0.5, "programmed": 0.5, "unabsorbed": 0.775, "duration": 0
  }, {
    "timestamp": "2018-09-04T19:45:11-05:00", "_type": "Bolus", "amount": 0.5, "programmed": 0.5, "unabsorbed": 0.3, "duration": 0
  }, {
    "timestamp": "2018-09-04T19:34:55-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T19:34:55-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.8
  }, {
    "timestamp": "2018-09-04T19:19:39-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T19:19:39-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T19:04:41-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T19:04:41-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T18:50:22-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T18:50:22-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T18:44:44-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T18:44:44-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T18:34:47-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T18:34:47-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T18:19:36-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T18:19:36-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T18:05:26-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T18:05:26-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T17:59:27-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T17:59:27-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.85
  }, {
    "timestamp": "2018-09-04T17:53:07-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T17:53:07-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.45
  }, {
    "timestamp": "2018-09-04T17:40:27-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T17:40:27-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.15
  }, {
    "timestamp": "2018-09-04T17:29:36-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T17:29:36-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T17:25:39-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T17:25:39-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.85
  }, {
    "timestamp": "2018-09-04T17:23:20-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T17:23:20-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.1
  }, {
    "timestamp": "2018-09-04T16:59:48-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T16:59:48-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T16:39:28-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T16:39:28-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.25
  }, {
    "timestamp": "2018-09-04T16:29:50-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T16:29:50-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T16:25:16-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T16:25:16-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.3
  }, {
    "timestamp": "2018-09-04T16:21:23-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T16:21:23-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.5
  }, {
    "timestamp": "2018-09-04T16:17:43-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T16:17:43-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T16:12:29-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1.675, "duration": 0
  }, {
    "timestamp": "2018-09-04T16:12:03-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T16:12:03-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.75
  }, {
    "timestamp": "2018-09-04T15:45:29-05:00", "_type": "TempBasalDuration", "duration (min)": 0
  }, {
    "timestamp": "2018-09-04T15:45:29-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T15:31:00-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1.975, "duration": 0
  }, {
    "timestamp": "2018-09-04T15:29:40-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T15:29:40-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.6
  }, {
    "timestamp": "2018-09-04T15:14:39-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T15:14:39-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.2
  }, {
    "timestamp": "2018-09-04T15:10:36-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.125, "duration": 0
  }, {
    "timestamp": "2018-09-04T15:10:10-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T15:10:10-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.9
  }, {
    "timestamp": "2018-09-04T15:07:14-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T15:07:14-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.15
  }, {
    "timestamp": "2018-09-04T15:04:59-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 2.075, "duration": 0
  }, {
    "timestamp": "2018-09-04T15:04:40-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T15:04:40-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.8
  }, {
    "timestamp": "2018-09-04T14:55:03-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T14:55:03-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.45
  }, {
    "timestamp": "2018-09-04T14:34:52-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T14:34:52-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.9
  }, {
    "timestamp": "2018-09-04T14:29:26-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T14:29:26-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.35
  }, {
    "timestamp": "2018-09-04T14:27:35-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T14:27:35-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.45
  }, {
    "timestamp": "2018-09-04T14:25:26-05:00", "_type": "Bolus", "amount": 0.3, "programmed": 0.3, "unabsorbed": 2.125, "duration": 0
  }, {
    "timestamp": "2018-09-04T14:24:42-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T14:24:42-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.075
  }, {
    "timestamp": "2018-09-04T14:11:17-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T14:11:17-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2
  }, {
    "timestamp": "2018-09-04T14:10:04-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T14:10:04-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.025
  }, {
    "timestamp": "2018-09-04T13:59:51-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:59:51-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.4
  }, {
    "timestamp": "2018-09-04T13:39:31-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:39:31-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T13:36:47-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 2.275, "duration": 0
  }, {
    "timestamp": "2018-09-04T13:35:31-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:35:31-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1
  }, {
    "timestamp": "2018-09-04T13:35:07-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:35:07-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1
  }, {
    "timestamp": "2018-09-04T13:34:50-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:34:50-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1
  }, {
    "timestamp": "2018-09-04T13:32:24-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 2.075, "duration": 0
  }, {
    "timestamp": "2018-09-04T13:29:57-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:29:57-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.8
  }, {
    "timestamp": "2018-09-04T13:24:58-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 1.925, "duration": 0
  }, {
    "timestamp": "2018-09-04T13:24:40-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:24:40-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.95
  }, {
    "timestamp": "2018-09-04T13:20:23-05:00", "_type": "Bolus", "amount": 0.3, "programmed": 0.3, "unabsorbed": 1.65, "duration": 0
  }, {
    "timestamp": "2018-09-04T13:20:03-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:20:03-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.8
  }, {
    "timestamp": "2018-09-04T13:14:54-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 1.475, "duration": 0
  }, {
    "timestamp": "2018-09-04T13:14:33-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:14:33-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.325
  }, {
    "timestamp": "2018-09-04T13:09:56-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:09:56-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.65
  }, {
    "timestamp": "2018-09-04T13:05:26-05:00", "_type": "Bolus", "amount": 0.2, "programmed": 0.2, "unabsorbed": 1.325, "duration": 0
  }, {
    "timestamp": "2018-09-04T13:05:02-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T13:05:02-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.15
  }, {
    "timestamp": "2018-09-04T12:56:47-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T12:56:47-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.35
  }, {
    "timestamp": "2018-09-04T12:55:05-05:00", "_type": "Bolus", "amount": 0.3, "programmed": 0.3, "unabsorbed": 1.075, "duration": 0
  }, {
    "timestamp": "2018-09-04T12:54:44-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T12:54:44-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.8
  }, {
    "timestamp": "2018-09-04T12:33:51-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T12:33:51-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.75
  }, {
    "timestamp": "2018-09-04T12:25:26-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1.125, "duration": 0
  }, {
    "timestamp": "2018-09-04T12:25:04-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T12:25:04-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.1
  }, {
    "timestamp": "2018-09-04T12:19:40-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T12:19:40-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.45
  }, {
    "timestamp": "2018-09-04T12:15:10-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1.075, "duration": 0
  }, {
    "timestamp": "2018-09-04T12:10:16-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 1, "duration": 0
  }, {
    "timestamp": "2018-09-04T12:09:56-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T12:09:56-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.075
  }, {
    "timestamp": "2018-09-04T12:05:18-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.925, "duration": 0
  }, {
    "timestamp": "2018-09-04T12:04:58-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T12:04:58-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.125
  }, {
    "timestamp": "2018-09-04T11:59:57-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T11:59:57-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.15
  }, {
    "timestamp": "2018-09-04T11:55:13-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.875, "duration": 0
  }, {
    "timestamp": "2018-09-04T11:49:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T11:49:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.6
  }, {
    "timestamp": "2018-09-04T11:46:06-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.825, "duration": 0
  }, {
    "timestamp": "2018-09-04T11:44:38-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T11:44:38-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.1
  }, {
    "timestamp": "2018-09-04T11:29:59-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T11:29:59-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.6
  }, {
    "timestamp": "2018-09-04T11:22:39-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.85, "duration": 0
  }, {
    "timestamp": "2018-09-04T11:22:20-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T11:22:20-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.05
  }, {
    "timestamp": "2018-09-04T11:09:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T11:09:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.7
  }, {
    "timestamp": "2018-09-04T11:01:50-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.85, "duration": 0
  }, {
    "timestamp": "2018-09-04T10:54:56-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T10:54:56-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.6
  }, {
    "timestamp": "2018-09-04T10:35:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T10:35:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.55
  }, {
    "timestamp": "2018-09-04T10:16:26-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T10:16:26-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.3
  }, {
    "timestamp": "2018-09-04T10:15:22-05:00", "_type": "PumpResume"
  }, {
    "timestamp": "2018-09-04T09:35:13-05:00", "_type": "PumpSuspend"
  }, {
    "timestamp": "2018-09-04T09:34:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T09:34:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.3
  }, {
    "timestamp": "2018-09-04T09:15:00-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T09:15:00-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.5
  }, {
    "timestamp": "2018-09-04T08:54:46-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:54:46-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T08:40:26-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:40:26-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }, {
    "timestamp": "2018-09-04T08:38:19-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:38:19-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1
  }, {
    "timestamp": "2018-09-04T08:36:47-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:36:47-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T08:36:15-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:36:15-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T08:35:54-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:35:54-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T08:35:36-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:35:36-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.05
  }, {
    "timestamp": "2018-09-04T08:33:20-05:00", "_type": "Bolus", "amount": 0.5, "programmed": 0.5, "unabsorbed": 0.9, "duration": 0
  }, {
    "timestamp": "2018-09-04T08:31:16-05:00", "_type": "Bolus", "amount": 0.3, "programmed": 0.3, "unabsorbed": 0.55, "duration": 0
  }, {
    "timestamp": "2018-09-04T08:30:59-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:30:59-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.8
  }, {
    "timestamp": "2018-09-04T08:28:03-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.45, "duration": 0
  }, {
    "timestamp": "2018-09-04T08:27:40-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:27:40-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.025
  }, {
    "timestamp": "2018-09-04T08:24:52-05:00", "_type": "Bolus", "amount": 0.3, "programmed": 0.3, "unabsorbed": 0.15, "duration": 0
  }, {
    "timestamp": "2018-09-04T08:24:34-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:24:34-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 2.6
  }, {
    "timestamp": "2018-09-04T08:20:55-05:00", "_type": "Bolus", "amount": 0.1, "programmed": 0.1, "unabsorbed": 0.05, "duration": 0
  }, {
    "timestamp": "2018-09-04T08:14:39-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:14:39-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.55
  }, {
    "timestamp": "2018-09-04T08:05:06-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T08:05:06-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.15
  }, {
    "timestamp": "2018-09-04T07:49:33-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T07:49:33-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.85
  }, {
    "timestamp": "2018-09-04T07:39:45-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T07:39:45-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.35
  }, {
    "timestamp": "2018-09-04T07:34:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T07:34:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0.85
  }, {
    "timestamp": "2018-09-04T07:31:14-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T07:31:14-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 1.1
  }, {
    "timestamp": "2018-09-04T07:29:37-05:00", "_type": "TempBasalDuration", "duration (min)": 30
  }, {
    "timestamp": "2018-09-04T07:29:37-05:00", "_type": "TempBasal", "temp": "absolute", "rate": 0
  }
]
EOT

  cat >autotune.data.json <<EOT
{
  "CRData": [
    {
      "CRInitialIOB": -1.374,
      "CRInitialBG": 46,
      "CRInitialCarbTime": "2018-09-05T00:28:11.742Z",
      "CREndIOB": -1.136,
      "CREndBG": 138,
      "CREndTime": "2018-09-05T01:38:12.059Z",
      "CRCarbs": 30,
      "CRInsulin": -0.35
    },
    {
      "CRInitialIOB": -0.916,
      "CRInitialBG": 103,
      "CRInitialCarbTime": "2018-09-05T02:03:12.202Z",
      "CREndIOB": -0.085,
      "CREndBG": 145,
      "CREndTime": "2018-09-05T04:58:10.778Z",
      "CRCarbs": 62,
      "CRInsulin": 0
    }
  ],
  "CSFGlucoseData": [
    {
      "glucose": 103,
      "trend": 6.668422684640288,
      "noise": 1,
      "rssi": -66,
      "unfiltered": 142912,
      "_id": "5b8e861a82bf9b6cf6706b7f",
      "device": "xdripjs://RigName",
      "date": 1536067092481,
      "dateString": "2018-09-04T13:18:12.481Z",
      "sgv": 103,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 136160,
      "avgDelta": "2.50",
      "BGI": 0.95,
      "deviation": "1.55",
      "mealAbsorption": "start",
      "mealCarbs": 15
    },
    {
      "glucose": 116,
      "trend": 15.330471645292878,
      "noise": 1,
      "rssi": -72,
      "unfiltered": 156448,
      "_id": "5b8e874782bf9b6cf67076e1",
      "device": "xdripjs://RigName",
      "date": 1536067392586,
      "dateString": "2018-09-04T13:23:12.586Z",
      "sgv": 116,
      "direction": "FortyFiveUp",
      "type": "sgv",
      "filtered": 140992,
      "avgDelta": "5.50",
      "BGI": 1,
      "deviation": "4.50",
      "mealCarbs": 15
    },
    {
      "glucose": 130,
      "trend": 22.662058714728005,
      "noise": 1,
      "rssi": -73,
      "unfiltered": 170944,
      "_id": "5b8e887282bf9b6cf670823e",
      "device": "xdripjs://RigName",
      "date": 1536067692618,
      "dateString": "2018-09-04T13:28:12.618Z",
      "sgv": 130,
      "direction": "SingleUp",
      "type": "sgv",
      "filtered": 149280,
      "avgDelta": "8.75",
      "BGI": 1,
      "deviation": "7.75",
      "mealCarbs": 15
    },
    {
      "glucose": 142,
      "trend": 26.667911169187896,
      "noise": 1,
      "rssi": -62,
      "unfiltered": 182304,
      "_id": "5b8e89a082bf9b6cf6708e14",
      "device": "xdripjs://RigName",
      "date": 1536067992439,
      "dateString": "2018-09-04T13:33:12.439Z",
      "sgv": 142,
      "direction": "SingleUp",
      "type": "sgv",
      "filtered": 161056,
      "avgDelta": "10.75",
      "BGI": 1,
      "deviation": "9.75",
      "mealCarbs": 15
    },
    {
      "glucose": 145,
      "trend": 19.32678370107908,
      "noise": 1,
      "rssi": -66,
      "unfiltered": 185504,
      "_id": "5b8e8aca82bf9b6cf67099bc",
      "device": "xdripjs://RigName",
      "date": 1536068292891,
      "dateString": "2018-09-04T13:38:12.891Z",
      "sgv": 145,
      "direction": "FortyFiveUp",
      "type": "sgv",
      "filtered": 173888,
      "avgDelta": "10.50",
      "BGI": 1,
      "deviation": "9.50",
      "mealCarbs": 15
    },
    {
      "glucose": 151,
      "trend": 14.003889969435955,
      "noise": 1,
      "rssi": -75,
      "unfiltered": 191808,
      "_id": "5b8e8bf882bf9b6cf670a560",
      "device": "xdripjs://RigName",
      "date": 1536068592368,
      "dateString": "2018-09-04T13:43:12.368Z",
      "sgv": 151,
      "direction": "FortyFiveUp",
      "type": "sgv",
      "filtered": 184352,
      "avgDelta": "8.75",
      "BGI": 0.95,
      "deviation": "7.80",
      "mealCarbs": 15
    },
    {
      "glucose": 156,
      "trend": 10.00111123458162,
      "noise": 1,
      "rssi": -71,
      "unfiltered": 197216,
      "_id": "5b8e8d2282bf9b6cf670b098",
      "device": "xdripjs://RigName",
      "date": 1536068892339,
      "dateString": "2018-09-04T13:48:12.339Z",
      "sgv": 156,
      "direction": "FortyFiveUp",
      "type": "sgv",
      "filtered": 191008,
      "avgDelta": "6.50",
      "BGI": 0.95,
      "deviation": "5.55",
      "mealCarbs": 15
    }
  ],
  "ISFGlucoseData": [
    {
      "glucose": 221,
      "trend": -0.6668526444597327,
      "noise": 1,
      "rssi": -52,
      "unfiltered": 265984,
      "_id": "5b8eda7a82bf9b6cf673a452",
      "device": "xdripjs://RigName",
      "date": 1536088692777,
      "dateString": "2018-09-04T19:18:12.777Z",
      "sgv": 221,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 266688,
      "avgDelta": "0.00",
      "BGI": -2.7,
      "deviation": "2.70"
    },
    {
      "glucose": 223,
      "trend": 0.6667526036689173,
      "noise": 1,
      "rssi": -54,
      "unfiltered": 267968,
      "_id": "5b8edba682bf9b6cf673af8f",
      "device": "xdripjs://RigName",
      "date": 1536088992748,
      "dateString": "2018-09-04T19:23:12.748Z",
      "sgv": 223,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 266432,
      "avgDelta": "0.00",
      "BGI": -2.65,
      "deviation": "2.65"
    },
    {
      "glucose": 224,
      "trend": 2.6664740879825346,
      "noise": 1,
      "rssi": -77,
      "unfiltered": 269248,
      "_id": "5b8edcd382bf9b6cf673ba6d",
      "device": "xdripjs://RigName",
      "date": 1536089292875,
      "dateString": "2018-09-04T19:28:12.875Z",
      "sgv": 224,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 266624,
      "avgDelta": "0.25",
      "BGI": -2.55,
      "deviation": "2.80"
    }
  ],
  "basalGlucoseData": [
    {
      "glucose": 100,
      "trend": 1.332699560653378,
      "noise": 1,
      "rssi": -61,
      "unfiltered": 137920,
      "_id": "5b8e4f0d82bf9b6cf66e5b1f",
      "device": "xdripjs://RigName",
      "date": 1536052993966,
      "dateString": "2018-09-04T09:23:13.966Z",
      "sgv": 100,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 136928,
      "avgDelta": "0.25",
      "BGI": 1,
      "deviation": "-0.75"
    },
    {
      "glucose": 101,
      "trend": 1.3339113615900222,
      "noise": 1,
      "rssi": -62,
      "unfiltered": 138368,
      "_id": "5b8e503382bf9b6cf66e662b",
      "device": "xdripjs://RigName",
      "date": 1536053293158,
      "dateString": "2018-09-04T09:28:13.158Z",
      "sgv": 101,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 137312,
      "avgDelta": "0.50",
      "BGI": 1.05,
      "deviation": "-0.55"
    },
    {
      "glucose": 101,
      "trend": 1.3329852760668048,
      "noise": 1,
      "rssi": -62,
      "unfiltered": 138752,
      "_id": "5b8e515e82bf9b6cf66e7186",
      "device": "xdripjs://RigName",
      "date": 1536053593843,
      "dateString": "2018-09-04T09:33:13.843Z",
      "sgv": 101,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 137920,
      "avgDelta": "0.50",
      "BGI": 1.1,
      "deviation": "-0.60"
    },
    {
      "glucose": 102,
      "trend": 1.3334948343743853,
      "noise": 1,
      "rssi": -61,
      "unfiltered": 139744,
      "_id": "5b8e528b82bf9b6cf66e7d0d",
      "device": "xdripjs://RigName",
      "date": 1536053893857,
      "dateString": "2018-09-04T09:38:13.857Z",
      "sgv": 102,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 138592,
      "avgDelta": "0.50",
      "BGI": 1.1,
      "deviation": "-0.60"
    },
    {
      "glucose": 103,
      "trend": 1.9984367783422747,
      "noise": 1,
      "rssi": -62,
      "unfiltered": 140800,
      "_id": "5b8e53b782bf9b6cf66e8876",
      "device": "xdripjs://RigName",
      "date": 1536054193862,
      "dateString": "2018-09-04T09:43:13.862Z",
      "sgv": 103,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 139296,
      "avgDelta": "0.75",
      "BGI": 1.15,
      "deviation": "-0.40"
    },
    {
      "glucose": 104,
      "trend": 1.999935557632032,
      "noise": 1,
      "rssi": -66,
      "unfiltered": 141888,
      "_id": "5b8e54e382bf9b6cf66e93ae",
      "device": "xdripjs://RigName",
      "date": 1536054493872,
      "dateString": "2018-09-04T09:48:13.872Z",
      "sgv": 104,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 140160,
      "avgDelta": "0.75",
      "BGI": 1.2,
      "deviation": "-0.45"
    },
    {
      "glucose": 108,
      "trend": 4.002441489308478,
      "noise": 1,
      "rssi": -64,
      "unfiltered": 145792,
      "_id": "5b8e560f82bf9b6cf66e9ed8",
      "device": "xdripjs://RigName",
      "date": 1536054793308,
      "dateString": "2018-09-04T09:53:13.308Z",
      "sgv": 108,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 141504,
      "avgDelta": "1.75",
      "BGI": 1.25,
      "deviation": "0.50"
    },
    {
      "glucose": 109,
      "trend": 4.002463738790322,
      "noise": 1,
      "rssi": -71,
      "unfiltered": 147264,
      "_id": "5b8e573c82bf9b6cf66eaa35",
      "device": "xdripjs://RigName",
      "date": 1536055093308,
      "dateString": "2018-09-04T09:58:13.308Z",
      "sgv": 109,
      "direction": "Flat",
      "type": "sgv",
      "filtered": 143456,
      "avgDelta": "1.75",
      "BGI": 1.2,
      "deviation": "0.55"
    }
  ]
}
EOT

    cat >autotune.treatments.json <<EOT
[
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T03:44:43-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f985f82bf9b6cf67a789c",
    "duration": 60,
    "raw_duration": {
      "duration (min)": 60,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T03:44:43-05:00"
    },
    "timestamp": "2018-09-05T03:44:43-05:00",
    "absolute": 0,
    "rate": 0,
    "raw_rate": {
      "rate": 0,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T03:44:43-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T03:29:47-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f94a582bf9b6cf67a55b2",
    "duration": 60,
    "raw_duration": {
      "duration (min)": 60,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T03:29:47-05:00"
    },
    "timestamp": "2018-09-05T03:29:47-05:00",
    "absolute": 0,
    "rate": 0,
    "raw_rate": {
      "rate": 0,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T03:29:47-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T03:14:21-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f90b382bf9b6cf67a31cd",
    "duration": 60,
    "raw_duration": {
      "duration (min)": 60,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T03:14:21-05:00"
    },
    "timestamp": "2018-09-05T03:14:21-05:00",
    "absolute": 0,
    "rate": 0,
    "raw_rate": {
      "rate": 0,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T03:14:21-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T03:10:30-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f8fff82bf9b6cf67a2b41",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T03:10:30-05:00"
    },
    "timestamp": "2018-09-05T03:10:30-05:00",
    "absolute": 0,
    "rate": 0,
    "raw_rate": {
      "rate": 0,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T03:10:30-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T02:54:45-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f8f0082bf9b6cf67a224d",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T02:54:45-05:00"
    },
    "timestamp": "2018-09-05T02:54:45-05:00",
    "absolute": 0.1,
    "rate": 0.1,
    "raw_rate": {
      "rate": 0.1,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T02:54:45-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T02:49:42-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f8b1282bf9b6cf67a0101",
    "duration": 60,
    "raw_duration": {
      "duration (min)": 60,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T02:49:42-05:00"
    },
    "timestamp": "2018-09-05T02:49:42-05:00",
    "absolute": 0,
    "rate": 0,
    "raw_rate": {
      "rate": 0,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T02:49:42-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T02:34:58-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f87d082bf9b6cf679e371",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T02:34:58-05:00"
    },
    "timestamp": "2018-09-05T02:34:58-05:00",
    "absolute": 0.2,
    "rate": 0.2,
    "raw_rate": {
      "rate": 0.2,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T02:34:58-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T02:24:58-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f853482bf9b6cf679cbbb",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T02:24:58-05:00"
    },
    "timestamp": "2018-09-05T02:24:58-05:00",
    "absolute": 0.3,
    "rate": 0.3,
    "raw_rate": {
      "rate": 0.3,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T02:24:58-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T02:14:58-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f82d382bf9b6cf679b597",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T02:14:58-05:00"
    },
    "timestamp": "2018-09-05T02:14:58-05:00",
    "absolute": 0.5,
    "rate": 0.5,
    "raw_rate": {
      "rate": 0.5,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T02:14:58-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "NSCLIENT_ID": 1536115767681,
    "_id": "5b8f4438c09b910004e36513",
    "created_at": "2018-09-05T02:00:00Z",
    "eventType": "Meal Bolus",
    "glucose": 108,
    "glucoseType": "Finger",
    "carbs": 62,
    "units": "mg/dl",
    "enteredBy": "Jeremy"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T01:44:52-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f7c0782bf9b6cf679770b",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T01:44:52-05:00"
    },
    "timestamp": "2018-09-05T01:44:52-05:00",
    "absolute": 0.45,
    "rate": 0.45,
    "raw_rate": {
      "rate": 0.45,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T01:44:52-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T01:22:38-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f76e282bf9b6cf679484f",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T01:22:38-05:00"
    },
    "timestamp": "2018-09-05T01:22:38-05:00",
    "absolute": 0.6,
    "rate": 0.6,
    "raw_rate": {
      "rate": 0.6,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T01:22:38-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T01:19:43-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f75f282bf9b6cf6793fa8",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T01:19:43-05:00"
    },
    "timestamp": "2018-09-05T01:19:43-05:00",
    "absolute": 0.05,
    "rate": 0.05,
    "raw_rate": {
      "rate": 0.05,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T01:19:43-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "created_at": "2018-09-05T01:10:07.021Z",
    "duration": 0,
    "reason": "",
    "eventType": "Temporary Target",
    "enteredBy": "Jeremy",
    "_id": "5b8f2cef82bf9b6cf676983c"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T01:04:53-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f726f82bf9b6cf6791e84",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T01:04:53-05:00"
    },
    "timestamp": "2018-09-05T01:04:53-05:00",
    "absolute": 0.65,
    "rate": 0.65,
    "raw_rate": {
      "rate": 0.65,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T01:04:53-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T00:59:30-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f713f82bf9b6cf6791360",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T00:59:30-05:00"
    },
    "timestamp": "2018-09-05T00:59:30-05:00",
    "absolute": 0,
    "rate": 0,
    "raw_rate": {
      "rate": 0,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T00:59:30-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T00:54:54-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f705482bf9b6cf6790aad",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T00:54:54-05:00"
    },
    "timestamp": "2018-09-05T00:54:54-05:00",
    "absolute": 0.75,
    "rate": 0.75,
    "raw_rate": {
      "rate": 0.75,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T00:54:54-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T00:34:37-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f6b6782bf9b6cf678dd0f",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T00:34:37-05:00"
    },
    "timestamp": "2018-09-05T00:34:37-05:00",
    "absolute": 0.55,
    "rate": 0.55,
    "raw_rate": {
      "rate": 0.55,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T00:34:37-05:00"
    },
    "eventType": "Temp Basal"
  },
  {
    "insulin": null,
    "carbs": null,
    "enteredBy": "openaps://medtronic/723",
    "created_at": "2018-09-05T00:29:56-05:00",
    "medtronic": "mm://openaps/mm-format-ns-treatments/Temp Basal",
    "_id": "5b8f6a3b82bf9b6cf678d1c6",
    "duration": 30,
    "raw_duration": {
      "duration (min)": 30,
      "_type": "TempBasalDuration",
      "timestamp": "2018-09-05T00:29:56-05:00"
    },
    "timestamp": "2018-09-05T00:29:56-05:00",
    "absolute": 0.85,
    "rate": 0.85,
    "raw_rate": {
      "rate": 0.85,
      "temp": "absolute",
      "_type": "TempBasal",
      "timestamp": "2018-09-05T00:29:56-05:00"
    },
    "eventType": "Temp Basal"
  }
]
EOT

    cat >autotune.entries.json <<EOT
[
  {
    "glucose": 54,
    "trend": -1.3333362963028805,
    "noise": 1,
    "rssi": -78,
    "unfiltered": 96624,
    "_id": "5b8f9aa982bf9b6cf67a8df5",
    "device": "xdripjs://RigName",
    "date": 1536137891357,
    "dateString": "2018-09-05T08:58:11.357Z",
    "sgv": 54,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 96640
  },
  {
    "glucose": 53,
    "trend": -4.662957025299873,
    "noise": 1,
    "rssi": -78,
    "unfiltered": 95840,
    "_id": "5b8f997c82bf9b6cf67a82e7",
    "device": "xdripjs://RigName",
    "date": 1536137591464,
    "dateString": "2018-09-05T08:53:11.464Z",
    "sgv": 53,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 99072
  },
  {
    "glucose": 54,
    "trend": -5.330484485513853,
    "noise": 1,
    "rssi": -85,
    "unfiltered": 96560,
    "_id": "5b8f985082bf9b6cf67a77e6",
    "device": "xdripjs://RigName",
    "date": 1536137291320,
    "dateString": "2018-09-05T08:48:11.320Z",
    "sgv": 54,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 101856
  },
  {
    "glucose": 57,
    "trend": -4.667330464777213,
    "noise": 1,
    "rssi": -77,
    "unfiltered": 99648,
    "_id": "5b8f972482bf9b6cf67a6ce9",
    "device": "xdripjs://RigName",
    "date": 1536136991359,
    "dateString": "2018-09-05T08:43:11.359Z",
    "sgv": 57,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 104000
  },
  {
    "glucose": 61,
    "trend": -2.667876103833738,
    "noise": 1,
    "rssi": -95,
    "unfiltered": 103424,
    "_id": "5b8f95f982bf9b6cf67a61fe",
    "device": "xdripjs://RigName",
    "date": 1536136690748,
    "dateString": "2018-09-05T08:38:10.748Z",
    "sgv": 61,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 105552
  },
  {
    "glucose": 64,
    "trend": -2.667988803340322,
    "noise": 1,
    "rssi": -79,
    "unfiltered": 105696,
    "_id": "5b8f94cd82bf9b6cf67a572b",
    "device": "xdripjs://RigName",
    "date": 1536136390839,
    "dateString": "2018-09-05T08:33:10.839Z",
    "sgv": 64,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 107360
  },
  {
    "glucose": 65,
    "trend": -5.3303009843289155,
    "noise": 1,
    "rssi": -78,
    "unfiltered": 106592,
    "_id": "5b8f93a082bf9b6cf67a4c4b",
    "device": "xdripjs://RigName",
    "date": 1536136091487,
    "dateString": "2018-09-05T08:28:11.487Z",
    "sgv": 65,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 109936
  },
  {
    "glucose": 66,
    "trend": -5.997181324777355,
    "noise": 1,
    "rssi": -95,
    "unfiltered": 108096,
    "_id": "5b8f927582bf9b6cf67a41ad",
    "device": "xdripjs://RigName",
    "date": 1536135791156,
    "dateString": "2018-09-05T08:23:11.156Z",
    "sgv": 66,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 112736
  },
  {
    "glucose": 68,
    "trend": -6.993565919354194,
    "noise": 1,
    "rssi": -98,
    "unfiltered": 110016,
    "_id": "5b8f914882bf9b6cf67a36fb",
    "device": "xdripjs://RigName",
    "date": 1536135491285,
    "dateString": "2018-09-05T08:18:11.285Z",
    "sgv": 68,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 115072
  },
  {
    "glucose": 73,
    "trend": -3.996775934079842,
    "noise": 1,
    "rssi": -77,
    "unfiltered": 114544,
    "_id": "5b8f901d82bf9b6cf67a2c4e",
    "device": "xdripjs://RigName",
    "date": 1536135190975,
    "dateString": "2018-09-05T08:13:10.975Z",
    "sgv": 73,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 116896
  },
  {
    "glucose": 76,
    "trend": -3.9991735041424774,
    "noise": 1,
    "rssi": -69,
    "unfiltered": 116928,
    "_id": "5b8f8ef082bf9b6cf67a2172",
    "device": "xdripjs://RigName",
    "date": 1536134890733,
    "dateString": "2018-09-05T08:08:10.733Z",
    "sgv": 76,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 118608
  },
  {
    "glucose": 82,
    "trend": -3.9996889130845377,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 122864,
    "_id": "5b8f8b6c82bf9b6cf67a0434",
    "device": "xdripjs://RigName",
    "date": 1536133990547,
    "dateString": "2018-09-05T07:53:10.547Z",
    "sgv": 82,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 126352
  },
  {
    "glucose": 82,
    "trend": -6.666281503735339,
    "noise": 1,
    "rssi": -57,
    "unfiltered": 122928,
    "_id": "5b8f8a4182bf9b6cf679f977",
    "device": "xdripjs://RigName",
    "date": 1536133690633,
    "dateString": "2018-09-05T07:48:10.633Z",
    "sgv": 82,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 129408
  },
  {
    "glucose": 89,
    "trend": -4.000182230523835,
    "noise": 1,
    "rssi": -67,
    "unfiltered": 129216,
    "_id": "5b8f891482bf9b6cf679eee4",
    "device": "xdripjs://RigName",
    "date": 1536133390464,
    "dateString": "2018-09-05T07:43:10.464Z",
    "sgv": 89,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 132224
  },
  {
    "glucose": 90,
    "trend": -5.333582233837579,
    "noise": 1,
    "rssi": -64,
    "unfiltered": 129952,
    "_id": "5b8f87e882bf9b6cf679e452",
    "device": "xdripjs://RigName",
    "date": 1536133090477,
    "dateString": "2018-09-05T07:38:10.477Z",
    "sgv": 90,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 134560
  },
  {
    "glucose": 93,
    "trend": -3.332929678516713,
    "noise": 1,
    "rssi": -70,
    "unfiltered": 133568,
    "_id": "5b8f86bc82bf9b6cf679d9be",
    "device": "xdripjs://RigName",
    "date": 1536132790581,
    "dateString": "2018-09-05T07:33:10.581Z",
    "sgv": 93,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 136512
  },
  {
    "glucose": 95,
    "trend": -2.6669659595132345,
    "noise": 1,
    "rssi": -56,
    "unfiltered": 135488,
    "_id": "5b8f859082bf9b6cf679cf01",
    "device": "xdripjs://RigName",
    "date": 1536132490505,
    "dateString": "2018-09-05T07:28:10.505Z",
    "sgv": 95,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 138080
  },
  {
    "glucose": 97,
    "trend": -2.6670163421426367,
    "noise": 1,
    "rssi": -50,
    "unfiltered": 137824,
    "_id": "5b8f846582bf9b6cf679c41f",
    "device": "xdripjs://RigName",
    "date": 1536132190519,
    "dateString": "2018-09-05T07:23:10.519Z",
    "sgv": 97,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 139584
  },
  {
    "glucose": 98,
    "trend": -2.6668948343358263,
    "noise": 1,
    "rssi": -50,
    "unfiltered": 138560,
    "_id": "5b8f833882bf9b6cf679b947",
    "device": "xdripjs://RigName",
    "date": 1536131890472,
    "dateString": "2018-09-05T07:18:10.472Z",
    "sgv": 98,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 141184
  },
  {
    "glucose": 100,
    "trend": -3.3342298706985654,
    "noise": 1,
    "rssi": -55,
    "unfiltered": 140448,
    "_id": "5b8f820c82bf9b6cf679ae2b",
    "device": "xdripjs://RigName",
    "date": 1536131590606,
    "dateString": "2018-09-05T07:13:10.606Z",
    "sgv": 100,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 142944
  },
  {
    "glucose": 101,
    "trend": -3.3332296328558666,
    "noise": 1,
    "rssi": -57,
    "unfiltered": 142016,
    "_id": "5b8f80e082bf9b6cf679a36b",
    "device": "xdripjs://RigName",
    "date": 1536131290637,
    "dateString": "2018-09-05T07:08:10.637Z",
    "sgv": 101,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 144736
  },
  {
    "glucose": 103,
    "trend": -3.3359390724087814,
    "noise": 1,
    "rssi": -49,
    "unfiltered": 143520,
    "_id": "5b8f7fb482bf9b6cf6799886",
    "device": "xdripjs://RigName",
    "date": 1536130990549,
    "dateString": "2018-09-05T07:03:10.549Z",
    "sgv": 103,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 146464
  },
  {
    "glucose": 105,
    "trend": -3.332663097754785,
    "noise": 1,
    "rssi": -56,
    "unfiltered": 145760,
    "_id": "5b8f7e8982bf9b6cf6798dde",
    "device": "xdripjs://RigName",
    "date": 1536130690848,
    "dateString": "2018-09-05T06:58:10.848Z",
    "sgv": 105,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 148128
  },
  {
    "glucose": 106,
    "trend": -3.3343262215859837,
    "noise": 1,
    "rssi": -53,
    "unfiltered": 147424,
    "_id": "5b8f7d5c82bf9b6cf6798332",
    "device": "xdripjs://RigName",
    "date": 1536130390609,
    "dateString": "2018-09-05T06:53:10.609Z",
    "sgv": 106,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 149792
  },
  {
    "glucose": 108,
    "trend": -3.3308906801678773,
    "noise": 1,
    "rssi": -57,
    "unfiltered": 148864,
    "_id": "5b8f7c3182bf9b6cf67978a5",
    "device": "xdripjs://RigName",
    "date": 1536130091252,
    "dateString": "2018-09-05T06:48:11.252Z",
    "sgv": 108,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 151488
  },
  {
    "glucose": 109,
    "trend": -3.9992623582761397,
    "noise": 1,
    "rssi": -55,
    "unfiltered": 150496,
    "_id": "5b8f7b0482bf9b6cf6796dcc",
    "device": "xdripjs://RigName",
    "date": 1536129790667,
    "dateString": "2018-09-05T06:43:10.667Z",
    "sgv": 109,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 153280
  },
  {
    "glucose": 111,
    "trend": -3.332159672648634,
    "noise": 1,
    "rssi": -54,
    "unfiltered": 152512,
    "_id": "5b8f79d982bf9b6cf6796337",
    "device": "xdripjs://RigName",
    "date": 1536129490877,
    "dateString": "2018-09-05T06:38:10.877Z",
    "sgv": 111,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 155232
  },
  {
    "glucose": 113,
    "trend": -4.668840271192922,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 154272,
    "_id": "5b8f78ac82bf9b6cf679587c",
    "device": "xdripjs://RigName",
    "date": 1536129190592,
    "dateString": "2018-09-05T06:33:10.592Z",
    "sgv": 113,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 157472
  },
  {
    "glucose": 115,
    "trend": -4.66938528654461,
    "noise": 1,
    "rssi": -50,
    "unfiltered": 156416,
    "_id": "5b8f778082bf9b6cf6794df5",
    "device": "xdripjs://RigName",
    "date": 1536128890501,
    "dateString": "2018-09-05T06:28:10.501Z",
    "sgv": 115,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 160032
  },
  {
    "glucose": 117,
    "trend": -5.334477282350549,
    "noise": 1,
    "rssi": -50,
    "unfiltered": 158496,
    "_id": "5b8f765482bf9b6cf679432c",
    "device": "xdripjs://RigName",
    "date": 1536128590560,
    "dateString": "2018-09-05T06:23:10.560Z",
    "sgv": 117,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 162560
  },
  {
    "glucose": 119,
    "trend": -3.998049840133535,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 160672,
    "_id": "5b8f752982bf9b6cf6793852",
    "device": "xdripjs://RigName",
    "date": 1536128291011,
    "dateString": "2018-09-05T06:18:11.011Z",
    "sgv": 119,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 164704
  },
  {
    "glucose": 122,
    "trend": -2.665499770100645,
    "noise": 1,
    "rssi": -52,
    "unfiltered": 163904,
    "_id": "5b8f73fd82bf9b6cf6792cf1",
    "device": "xdripjs://RigName",
    "date": 1536127991025,
    "dateString": "2018-09-05T06:13:11.025Z",
    "sgv": 122,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 166368
  },
  {
    "glucose": 124,
    "trend": -2.666480013065752,
    "noise": 1,
    "rssi": -60,
    "unfiltered": 166016,
    "_id": "5b8f72d182bf9b6cf67921ff",
    "device": "xdripjs://RigName",
    "date": 1536127690753,
    "dateString": "2018-09-05T06:08:10.753Z",
    "sgv": 124,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 167840
  },
  {
    "glucose": 125,
    "trend": -2.6681252417988497,
    "noise": 1,
    "rssi": -54,
    "unfiltered": 166976,
    "_id": "5b8f71a482bf9b6cf6791712",
    "device": "xdripjs://RigName",
    "date": 1536127390572,
    "dateString": "2018-09-05T06:03:10.572Z",
    "sgv": 125,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 169376
  },
  {
    "glucose": 127,
    "trend": -3.333929736319497,
    "noise": 1,
    "rssi": -57,
    "unfiltered": 168512,
    "_id": "5b8f707982bf9b6cf6790c09",
    "device": "xdripjs://RigName",
    "date": 1536127090631,
    "dateString": "2018-09-05T05:58:10.631Z",
    "sgv": 127,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 171072
  },
  {
    "glucose": 129,
    "trend": -3.33370374486054,
    "noise": 1,
    "rssi": -53,
    "unfiltered": 170368,
    "_id": "5b8f6f4d82bf9b6cf6790124",
    "device": "xdripjs://RigName",
    "date": 1536126790690,
    "dateString": "2018-09-05T05:53:10.690Z",
    "sgv": 129,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 172896
  },
  {
    "glucose": 130,
    "trend": -3.9997111319738017,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 171904,
    "_id": "5b8f6e2182bf9b6cf678f64d",
    "device": "xdripjs://RigName",
    "date": 1536126491064,
    "dateString": "2018-09-05T05:48:11.064Z",
    "sgv": 130,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 174944
  },
  {
    "glucose": 132,
    "trend": -3.999586709373365,
    "noise": 1,
    "rssi": -52,
    "unfiltered": 174016,
    "_id": "5b8f6cf582bf9b6cf678eb7b",
    "device": "xdripjs://RigName",
    "date": 1536126190792,
    "dateString": "2018-09-05T05:43:10.792Z",
    "sgv": 132,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 177088
  },
  {
    "glucose": 134,
    "trend": -3.333870456906946,
    "noise": 1,
    "rssi": -52,
    "unfiltered": 175488,
    "_id": "5b8f6bc982bf9b6cf678e09f",
    "device": "xdripjs://RigName",
    "date": 1536125890790,
    "dateString": "2018-09-05T05:38:10.790Z",
    "sgv": 134,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 179008
  },
  {
    "glucose": 136,
    "trend": -3.3326482889628246,
    "noise": 1,
    "rssi": -52,
    "unfiltered": 178048,
    "_id": "5b8f6a9d82bf9b6cf678d56f",
    "device": "xdripjs://RigName",
    "date": 1536125590999,
    "dateString": "2018-09-05T05:33:10.999Z",
    "sgv": 136,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 180576
  },
  {
    "glucose": 138,
    "trend": -2.0001511225292576,
    "noise": 1,
    "rssi": -54,
    "unfiltered": 180032,
    "_id": "5b8f697382bf9b6cf678ca6c",
    "device": "xdripjs://RigName",
    "date": 1536125290699,
    "dateString": "2018-09-05T05:28:10.699Z",
    "sgv": 138,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 181792
  },
  {
    "glucose": 139,
    "trend": -1.9996600577901755,
    "noise": 1,
    "rssi": -53,
    "unfiltered": 181184,
    "_id": "5b8f684582bf9b6cf678bf35",
    "device": "xdripjs://RigName",
    "date": 1536124990935,
    "dateString": "2018-09-05T05:23:10.935Z",
    "sgv": 139,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 183008
  },
  {
    "glucose": 141,
    "trend": -2.0000888928396816,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 182880,
    "_id": "5b8f671882bf9b6cf678b42a",
    "device": "xdripjs://RigName",
    "date": 1536124690814,
    "dateString": "2018-09-05T05:18:10.814Z",
    "sgv": 141,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 184352
  },
  {
    "glucose": 141,
    "trend": -2.666699259657618,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 183328,
    "_id": "5b8f65ec82bf9b6cf678a908",
    "device": "xdripjs://RigName",
    "date": 1536124390767,
    "dateString": "2018-09-05T05:13:10.767Z",
    "sgv": 141,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 185664
  },
  {
    "glucose": 142,
    "trend": -2.666699259657618,
    "noise": 1,
    "rssi": -54,
    "unfiltered": 184512,
    "_id": "5b8f64c182bf9b6cf6789dbe",
    "device": "xdripjs://RigName",
    "date": 1536124090782,
    "dateString": "2018-09-05T05:08:10.782Z",
    "sgv": 142,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 186720
  },
  {
    "glucose": 144,
    "trend": -1.9998622317129264,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 186592,
    "_id": "5b8f639582bf9b6cf6789262",
    "device": "xdripjs://RigName",
    "date": 1536123790854,
    "dateString": "2018-09-05T05:03:10.854Z",
    "sgv": 144,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 187552
  },
  {
    "glucose": 145,
    "trend": -1.9998622317129264,
    "noise": 1,
    "rssi": -52,
    "unfiltered": 187200,
    "_id": "5b8f626982bf9b6cf678870a",
    "device": "xdripjs://RigName",
    "date": 1536123490778,
    "dateString": "2018-09-05T04:58:10.778Z",
    "sgv": 145,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 188512
  },
  {
    "glucose": 146,
    "trend": -2.6671912142721403,
    "noise": 1,
    "rssi": -51,
    "unfiltered": 188576,
    "_id": "5b8f613d82bf9b6cf6787c09",
    "device": "xdripjs://RigName",
    "date": 1536123190793,
    "dateString": "2018-09-05T04:53:10.793Z",
    "sgv": 146,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 190016
  },
  {
    "glucose": 147,
    "trend": -4.001920922042581,
    "noise": 1,
    "rssi": -64,
    "unfiltered": 189056,
    "_id": "5b8f601182bf9b6cf67870f3",
    "device": "xdripjs://RigName",
    "date": 1536122890792,
    "dateString": "2018-09-05T04:48:10.792Z",
    "sgv": 147,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 191936
  },
  {
    "glucose": 148,
    "trend": -2.666752595361406,
    "noise": 1,
    "rssi": -68,
    "unfiltered": 190240,
    "_id": "5b8f5ee582bf9b6cf678661f",
    "device": "xdripjs://RigName",
    "date": 1536122590716,
    "dateString": "2018-09-05T04:43:10.716Z",
    "sgv": 148,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 193856
  },
  {
    "glucose": 150,
    "trend": -2.6664000266640002,
    "noise": 1,
    "rssi": -59,
    "unfiltered": 192832,
    "_id": "5b8f5db982bf9b6cf6785b03",
    "device": "xdripjs://RigName",
    "date": 1536122290970,
    "dateString": "2018-09-05T04:38:10.970Z",
    "sgv": 150,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 195424
  },
  {
    "glucose": 153,
    "trend": -0.6664008467733425,
    "noise": 1,
    "rssi": -58,
    "unfiltered": 195360,
    "_id": "5b8f5c8d82bf9b6cf6785020",
    "device": "xdripjs://RigName",
    "date": 1536121991224,
    "dateString": "2018-09-05T04:33:11.224Z",
    "sgv": 153,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 196256
  },
  {
    "glucose": 152,
    "trend": -0.666943818875844,
    "noise": 1,
    "rssi": -64,
    "unfiltered": 194720,
    "_id": "5b8f5b6182bf9b6cf6784464",
    "device": "xdripjs://RigName",
    "date": 1536121690745,
    "dateString": "2018-09-05T04:28:10.745Z",
    "sgv": 152,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 196288
  },
  {
    "glucose": 154,
    "trend": 1.333219269018095,
    "noise": 1,
    "rssi": -91,
    "unfiltered": 197088,
    "_id": "5b8f5a3582bf9b6cf67839aa",
    "device": "xdripjs://RigName",
    "date": 1536121390880,
    "dateString": "2018-09-05T04:23:10.880Z",
    "sgv": 154,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 195776
  },
  {
    "glucose": 154,
    "trend": 0.6669660603204105,
    "noise": 1,
    "rssi": -64,
    "unfiltered": 196576,
    "_id": "5b8f590a82bf9b6cf6782ebb",
    "device": "xdripjs://RigName",
    "date": 1536121090865,
    "dateString": "2018-09-05T04:18:10.865Z",
    "sgv": 154,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 195296
  },
  {
    "glucose": 153,
    "trend": -0.6667207451271048,
    "noise": 1,
    "rssi": -76,
    "unfiltered": 195968,
    "_id": "5b8f57de82bf9b6cf67823e9",
    "device": "xdripjs://RigName",
    "date": 1536120791119,
    "dateString": "2018-09-05T04:13:11.119Z",
    "sgv": 153,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 195488
  },
  {
    "glucose": 152,
    "trend": -2.0002355833020333,
    "noise": 1,
    "rssi": -57,
    "unfiltered": 195040,
    "_id": "5b8f56b182bf9b6cf67818e8",
    "device": "xdripjs://RigName",
    "date": 1536120490803,
    "dateString": "2018-09-05T04:08:10.803Z",
    "sgv": 152,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 196352
  },
  {
    "glucose": 153,
    "trend": -1.3329512206500802,
    "noise": 1,
    "rssi": -65,
    "unfiltered": 195648,
    "_id": "5b8f558582bf9b6cf6780e23",
    "device": "xdripjs://RigName",
    "date": 1536120191269,
    "dateString": "2018-09-05T04:03:11.269Z",
    "sgv": 153,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 197408
  },
  {
    "glucose": 154,
    "trend": -0.6665526121085947,
    "noise": 1,
    "rssi": -63,
    "unfiltered": 196608,
    "_id": "5b8f545982bf9b6cf678031a",
    "device": "xdripjs://RigName",
    "date": 1536119891192,
    "dateString": "2018-09-05T03:58:11.192Z",
    "sgv": 154,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 198016
  },
  {
    "glucose": 155,
    "trend": 1.3333777792593084,
    "noise": 1,
    "rssi": -73,
    "unfiltered": 197536,
    "_id": "5b8f532d82bf9b6cf677f818",
    "device": "xdripjs://RigName",
    "date": 1536119590909,
    "dateString": "2018-09-05T03:53:10.909Z",
    "sgv": 155,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 197952
  },
  {
    "glucose": 156,
    "trend": 1.9997178175968504,
    "noise": 1,
    "rssi": -72,
    "unfiltered": 198432,
    "_id": "5b8f520282bf9b6cf677ed50",
    "device": "xdripjs://RigName",
    "date": 1536119291011,
    "dateString": "2018-09-05T03:48:11.011Z",
    "sgv": 156,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 197280
  },
  {
    "glucose": 155,
    "trend": 3.337022597204687,
    "noise": 1,
    "rssi": -58,
    "unfiltered": 197952,
    "_id": "5b8f50d582bf9b6cf677e261",
    "device": "xdripjs://RigName",
    "date": 1536118991038,
    "dateString": "2018-09-05T03:43:11.038Z",
    "sgv": 155,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 195968
  },
  {
    "glucose": 154,
    "trend": 3.3376017551335093,
    "noise": 1,
    "rssi": -57,
    "unfiltered": 196256,
    "_id": "5b8f4faa82bf9b6cf677d771",
    "device": "xdripjs://RigName",
    "date": 1536118690939,
    "dateString": "2018-09-05T03:38:10.939Z",
    "sgv": 154,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 193856
  },
  {
    "glucose": 153,
    "trend": 6.00984947552934,
    "noise": 1,
    "rssi": -69,
    "unfiltered": 195136,
    "_id": "5b8f4e7d82bf9b6cf677cc6b",
    "device": "xdripjs://RigName",
    "date": 1536118390884,
    "dateString": "2018-09-05T03:33:10.884Z",
    "sgv": 153,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 190688
  },
  {
    "glucose": 150,
    "trend": 7.333773359734917,
    "noise": 1,
    "rssi": -77,
    "unfiltered": 192224,
    "_id": "5b8f4d5182bf9b6cf677c198",
    "device": "xdripjs://RigName",
    "date": 1536118092033,
    "dateString": "2018-09-05T03:28:12.033Z",
    "sgv": 150,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 186880
  },
  {
    "glucose": 148,
    "trend": 7.3331948174312265,
    "noise": 1,
    "rssi": -82,
    "unfiltered": 190368,
    "_id": "5b8f4c2682bf9b6cf677b697",
    "device": "xdripjs://RigName",
    "date": 1536117792090,
    "dateString": "2018-09-05T03:23:12.090Z",
    "sgv": 148,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 183232
  },
  {
    "glucose": 143,
    "trend": 5.999493376114906,
    "noise": 1,
    "rssi": -77,
    "unfiltered": 185120,
    "_id": "5b8f4af982bf9b6cf677abcd",
    "device": "xdripjs://RigName",
    "date": 1536117492359,
    "dateString": "2018-09-05T03:18:12.359Z",
    "sgv": 143,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 180256
  },
  {
    "glucose": 139,
    "trend": 3.332981518617479,
    "noise": 1,
    "rssi": -67,
    "unfiltered": 181280,
    "_id": "5b8f49cd82bf9b6cf677a091",
    "device": "xdripjs://RigName",
    "date": 1536117192087,
    "dateString": "2018-09-05T03:13:12.087Z",
    "sgv": 139,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 178016
  },
  {
    "glucose": 137,
    "trend": 4.667024471876177,
    "noise": 1,
    "rssi": -58,
    "unfiltered": 179456,
    "_id": "5b8f48a282bf9b6cf67795a6",
    "device": "xdripjs://RigName",
    "date": 1536116892073,
    "dateString": "2018-09-05T03:08:12.073Z",
    "sgv": 137,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 175776
  },
  {
    "glucose": 134,
    "trend": 4.665313725686218,
    "noise": 1,
    "rssi": -66,
    "unfiltered": 175872,
    "_id": "5b8f477582bf9b6cf6778aca",
    "device": "xdripjs://RigName",
    "date": 1536116592283,
    "dateString": "2018-09-05T03:03:12.283Z",
    "sgv": 134,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 173152
  },
  {
    "glucose": 133,
    "trend": 6.666185219956336,
    "noise": 1,
    "rssi": -59,
    "unfiltered": 175360,
    "_id": "5b8f464982bf9b6cf6777fee",
    "device": "xdripjs://RigName",
    "date": 1536116291992,
    "dateString": "2018-09-05T02:58:11.992Z",
    "sgv": 133,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 170016
  },
  {
    "glucose": 130,
    "trend": 7.334025991343627,
    "noise": 1,
    "rssi": -76,
    "unfiltered": 171776,
    "_id": "5b8f451e82bf9b6cf677753a",
    "device": "xdripjs://RigName",
    "date": 1536115992142,
    "dateString": "2018-09-05T02:53:12.142Z",
    "sgv": 130,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 166656
  },
  {
    "glucose": 127,
    "trend": 5.333380741162144,
    "noise": 1,
    "rssi": -64,
    "unfiltered": 168672,
    "_id": "5b8f43f182bf9b6cf6776a7d",
    "device": "xdripjs://RigName",
    "date": 1536115692022,
    "dateString": "2018-09-05T02:48:12.022Z",
    "sgv": 127,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 163616
  },
  {
    "glucose": 124,
    "trend": 5.335271815426271,
    "noise": 1,
    "rssi": -73,
    "unfiltered": 165824,
    "_id": "5b8f42c782bf9b6cf6775fa4",
    "device": "xdripjs://RigName",
    "date": 1536115391927,
    "dateString": "2018-09-05T02:43:11.927Z",
    "sgv": 124,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 160544
  },
  {
    "glucose": 119,
    "trend": 5.331875953905933,
    "noise": 1,
    "rssi": -72,
    "unfiltered": 160480,
    "_id": "5b8f419982bf9b6cf67754cd",
    "device": "xdripjs://RigName",
    "date": 1536115092227,
    "dateString": "2018-09-05T02:38:12.227Z",
    "sgv": 119,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 157120
  },
  {
    "glucose": 118,
    "trend": 7.333667422627031,
    "noise": 1,
    "rssi": -66,
    "unfiltered": 159744,
    "_id": "5b8f406d82bf9b6cf67749eb",
    "device": "xdripjs://RigName",
    "date": 1536114792030,
    "dateString": "2018-09-05T02:33:12.030Z",
    "sgv": 118,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 153600
  },
  {
    "glucose": 115,
    "trend": 7.331956554824705,
    "noise": 1,
    "rssi": -70,
    "unfiltered": 156736,
    "_id": "5b8f3f4282bf9b6cf6773ef4",
    "device": "xdripjs://RigName",
    "date": 1536114492254,
    "dateString": "2018-09-05T02:28:12.254Z",
    "sgv": 115,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 150400
  },
  {
    "glucose": 110,
    "trend": 4.0012537261675325,
    "noise": 1,
    "rssi": -60,
    "unfiltered": 151488,
    "_id": "5b8f3e1582bf9b6cf67733ec",
    "device": "xdripjs://RigName",
    "date": 1536114191981,
    "dateString": "2018-09-05T02:23:11.981Z",
    "sgv": 110,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 147744
  },
  {
    "glucose": 108,
    "trend": 2.667054871320159,
    "noise": 1,
    "rssi": -70,
    "unfiltered": 148544,
    "_id": "5b8f3cea82bf9b6cf677288e",
    "device": "xdripjs://RigName",
    "date": 1536113892071,
    "dateString": "2018-09-05T02:18:12.071Z",
    "sgv": 108,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 145024
  },
  {
    "glucose": 105,
    "trend": 1.332603362824586,
    "noise": 1,
    "rssi": -62,
    "unfiltered": 145664,
    "_id": "5b8f3cba82bf9b6cf67726a4",
    "device": "xdripjs://RigName",
    "date": 1536113592085,
    "dateString": "2018-09-05T02:13:12.085Z",
    "sgv": 105,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 142496
  },
  {
    "glucose": 105,
    "trend": -0.6661463323648306,
    "noise": 1,
    "rssi": -63,
    "unfiltered": 145728,
    "_id": "5b8f3cba82bf9b6cf67726a1",
    "device": "xdripjs://RigName",
    "date": 1536113292263,
    "dateString": "2018-09-05T02:08:12.263Z",
    "sgv": 105,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 142048
  },
  {
    "glucose": 103,
    "trend": -8.666474078353815,
    "noise": 1,
    "rssi": -65,
    "unfiltered": 144000,
    "_id": "5b8f396582bf9b6cf67707dd",
    "device": "xdripjs://RigName",
    "date": 1536112992202,
    "dateString": "2018-09-05T02:03:12.202Z",
    "sgv": 103,
    "direction": "Flat",
    "type": "sgv",
    "filtered": 145696
  },
  {
    "glucose": 102,
    "trend": -15.34131081495711,
    "noise": 1,
    "rssi": -77,
    "unfiltered": 142784,
    "_id": "5b8f383982bf9b6cf676fd2b",
    "device": "xdripjs://RigName",
    "date": 1536112691592,
    "dateString": "2018-09-05T01:58:11.592Z",
    "sgv": 102,
    "direction": "FortyFiveDown",
    "type": "sgv",
    "filtered": 153632
  },
  {
    "glucose": 106,
    "trend": -21.345168043170602,
    "noise": 1,
    "rssi": -79,
    "unfiltered": 146912,
    "_id": "5b8f370d82bf9b6cf676f25d",
    "device": "xdripjs://RigName",
    "date": 1536112391560,
    "dateString": "2018-09-05T01:53:11.560Z",
    "sgv": 106,
    "direction": "SingleDown",
    "type": "sgv",
    "filtered": 164032
  },
  {
    "glucose": 117,
    "trend": -17.997200435487812,
    "noise": 1,
    "rssi": -62,
    "unfiltered": 157952,
    "_id": "5b8f35e182bf9b6cf676e777",
    "device": "xdripjs://RigName",
    "date": 1536112092182,
    "dateString": "2018-09-05T01:48:12.182Z",
    "sgv": 117,
    "direction": "FortyFiveDown",
    "type": "sgv",
    "filtered": 174240
  },
  {
    "glucose": 126,
    "trend": -15.33529284297438,
    "noise": 1,
    "rssi": -73,
    "unfiltered": 167456,
    "_id": "5b8f34b782bf9b6cf676dcb0",
    "device": "xdripjs://RigName",
    "date": 1536111792060,
    "dateString": "2018-09-05T01:43:12.060Z",
    "sgv": 126,
    "direction": "FortyFiveDown",
    "type": "sgv",
    "filtered": 183072
  },
  {
    "glucose": 138,
    "trend": -12.001133440380482,
    "noise": 1,
    "rssi": -62,
    "unfiltered": 180224,
    "_id": "5b8f338982bf9b6cf676d1c7",
    "device": "xdripjs://RigName",
    "date": 1536111492059,
    "dateString": "2018-09-05T01:38:12.059Z",
    "sgv": 138,
    "direction": "FortyFiveDown",
    "type": "sgv",
    "filtered": 190400
  }
]
EOT

    cat >insulin_sensitivities.json <<EOT
{
  "units": "mg/dL",
  "user_preferred_units": "mg/dL",
  "sensitivities": [
    {
      "i": 0,
      "x": 0,
      "sensitivity": 100,
      "offset": 0,
      "start": "00:00:00"
    }
  ],
  "first": 1
}
EOT

    cat >temptargets.json <<EOT
[
  {
    "_id": "5b942fa682bf9b6cf6a48ae2",
    "enteredBy": "IFTTT-button",
    "eventType": "Temporary Target",
    "reason": "treat high",
    "targetTop": 80,
    "targetBottom": 80,
    "duration": 60,
    "created_at": "2018-09-04T20:23:02.888Z",
    "carbs": null,
    "insulin": null
  }
]
EOT

    cat >meal.json <<EOT
{"carbs":36,"nsCarbs":36,"bwCarbs":0,"journalCarbs":0,"mealCOB":0,"currentDeviation":-2.85,"maxDeviation":2.98,"minDeviation":-0.42,"slopeFromMaxDeviation":-1.15,"slopeFromMinDeviation":0,"allDeviations":[-3,0,1,2,1,3],"lastCarbTime":1536522546000,"bwFound":false}
EOT

    cat >carb_ratios.json <<EOT
{
  "first": 1,
  "units": "grams",
  "schedule": [
    {
      "x": 0,
      "i": 0,
      "start": "00:00:00",
      "offset": 0,
      "ratio": 15
    }
  ]
}
EOT

    cat >settings.json <<EOT
{
  "auto_off_duration_hrs": 0,
  "insulin_action_curve": 7,
  "insulinConcentration": 50,
  "maxBolus": 3,
  "maxBasal": 2.8,
  "rf_enable": false,
  "selected_pattern": 0
}
EOT

    cat >bg_targets.json <<EOT
{
  "units": "mg/dL",
  "user_preferred_units": "mg/dL",
  "targets": [
    {
      "i": 0,
      "high": 250,
      "start": "00:00:00",
      "low": 110,
      "offset": 0,
      "x": 0
    },
    {
      "i": 12,
      "high": 250,
      "start": "06:00:00",
      "low": 105,
      "offset": 360,
      "x": 1
    },
    {
      "i": 44,
      "high": 250,
      "start": "22:00:00",
      "low": 110,
      "offset": 1320,
      "x": 2
    }
  ],
  "first": 1
}
EOT

    cat >model.json <<EOT
"722"
EOT

}

main

exit 0

