var tz = require('timezone');
var calcMealCOB = require('oref0/lib/determine-basal/cob-autosens');

function diaCarbs(opts, time) {
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    if (typeof(opts.glucose) !== 'undefined') {
        var glucose_data = opts.glucose;
    }
    var carbs = 0;
    var boluses = 0;
    var carbDelay = 20 * 60 * 1000;
    var maxCarbs = 0;
    var mealCarbTime = time.getTime();
    if (!treatments) return {};

    //console.error(glucose_data);
    var iob_inputs = {
        profile: profile_data
    ,   history: opts.pumphistory
    };
    var COB_inputs = {
        glucose_data: glucose_data
    ,   iob_inputs: iob_inputs
    ,   basalprofile: opts.basalprofile
    ,   mealTime: mealCarbTime
    };
    var mealCOB = 0;

    treatments.forEach(function(treatment) {
        var now = time.getTime();
        var dia_ago = now - 1.5*profile_data.dia*60*60*1000;
        var treatmentDate = new Date(tz(treatment.timestamp));
        var treatmentTime = treatmentDate.getTime();
        if (treatmentTime > dia_ago && treatmentTime <= now) {
            if (treatment.carbs >= 1) {
                console.error(treatment.carbs, maxCarbs, treatmentDate);
                carbs += parseFloat(treatment.carbs);
                COB_inputs.mealTime = treatmentTime;
                var myCarbsAbsorbed = calcMealCOB(COB_inputs).carbsAbsorbed;
                var myMealCOB = Math.max(0, carbs - myCarbsAbsorbed);
                mealCOB = Math.max(mealCOB, myMealCOB);
                console.error(mealCOB);
            }
            if (treatment.bolus >= 0.1) {
                boluses += parseFloat(treatment.bolus);
            }
        }
    });

    return {
        carbs: Math.round( carbs * 1000 ) / 1000,
        boluses: Math.round( boluses * 1000 ) / 1000,
        mealCOB: Math.round( mealCOB )
    };
}

exports = module.exports = diaCarbs;

