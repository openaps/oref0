
//var tz = require('timezone');
//var find_meals = require('oref0/lib/meal/history');
//var sum = require('./total');

function generate (inputs) {

    var previous_autotune = inputs.previous_autotune;
    var basalprofile = previous_autotune.basalprofile;
    console.error(basalprofile);
    var isf_profile = previous_autotune.isfProfile;
    console.error(isf_profile);
    var isf = isf_profile.sensitivities[0].sensitivity;
    console.error(isf);
    var carb_ratio = previous_autotune.carb_ratio;
    console.error(carb_ratio);
    var csf = isf / carb_ratio;
    console.error(csf);
    var prepped_glucose = inputs.prepped_glucose;
    var csf_glucose = prepped_glucose.csf_glucose_data;
    //console.error(csf_glucose[0]);
    var isf_glucose = prepped_glucose.isf_glucose_data;
    //console.error(isf_glucose[0]);
    var basal_glucose = prepped_glucose.basal_glucose_data;
    //console.error(basal_glucose[0]);

    hourlybasalprofile = [];
    for (var i=0; i < 24; i++) {
        for (var j=0; j < basalprofile.length; ++j) {
            if (basalprofile[j].minutes <= i * 60) {
                hourlybasalprofile[i] = JSON.parse(JSON.stringify(basalprofile[j]));
            }
        }
        hourlybasalprofile[i].i=i;
        hourlybasalprofile[i].minutes=i*60;
    }
    console.error(hourlybasalprofile);


    /*
    var treatments = find_meals(inputs);

    var opts = {
        treatments: treatments
    , profile: inputs.profile
    , pumphistory: inputs.history
    , glucose: inputs.glucose
    , prepped_glucose: inputs.prepped_glucose
    , basalprofile: inputs.basalprofile
    };

    var clock = new Date(tz(inputs.clock));

    var autotune_prep_output = sum(opts, clock);
    return autotune_prep_output;
    */
    autotune_output = previous_autotune;
    autotune_output.basalprofile = basalprofile;
    isf_profile.sensitivities[0].sensitivity = isf;
    autotune_output.isf_profile = isf_profile;
    autotune_output.csf = csf;
    carb_ratio = isf / csf;
    autotune_output.carb_ratio = carb_ratio;

    return autotune_output;
}

exports = module.exports = generate;
