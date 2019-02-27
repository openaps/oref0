var autotune_prep = require('./autotune-prep');
var autotune = require('./autotune');

function run_autotune(inputs) {
        var prep_inputs = {
            history: inputs.treatments,
            profile: inputs.profile,
            pumpprofile: inputs.pump_profile,
            glucose: inputs.glucose_entries,
            carbs: {},
            categorize_uam_as_basal: inputs.categorize_uam_as_basal,
            tune_insulin_curve: inputs.tune_insulin_curve
        };
        var prepped_glucose = autotune_prep(prep_inputs);
        var autotune_inputs = {
            preppedGlucose: prepped_glucose,
            previousAutotune: inputs.autotune_profile,
            pumpProfile: inputs.pump_profile
        }
        var autotune_result = autotune(autotune_inputs);
        return autotune_result;
    }

module.exports = {
    run_autotune: run_autotune
}