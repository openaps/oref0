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
    //TODO: eliminate this
    var carbs_hr = 30;
    var maxCarbs = 0;
    var mealCarbTime = time.getTime();
    if (!treatments) return {};

    treatments.forEach(function(treatment) {
        now = time.getTime();
        var dia_ago = now - 1.5*profile_data.dia*60*60*1000;
        t = new Date(tz(treatment.timestamp)).getTime();
        if(t > dia_ago && t <= now) {
            if (treatment.carbs >= 1) {
                //console.error(treatment.carbs, maxCarbs, treatment.timestamp);
                if (parseInt(treatment.carbs) > maxCarbs) {
                    //mealCarbTime = treatment.timestamp;
                    maxCarbs = parseInt(treatment.carbs);
                    mealCarbTime = t;
                }
                //console.error(treatment.carbs, maxCarbs, treatment.timestamp);
                carbs += parseFloat(treatment.carbs);
            }
            if (treatment.bolus >= 0.1) {
                boluses += parseFloat(treatment.bolus);
            }
        }
    });
    //now = new Date().getTime();
    //hours = (now-firstCarbTime-carbDelay)/(60*60*1000);
    //decayed = carbs_hr*hours;
    //console.error(hours, decayed);
    // TODO: calculate mealCOB per https://github.com/openaps/oref0/issues/68
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
    var carbsAbsorbed = calcMealCOB(COB_inputs).carbsAbsorbed;
    var mealCOB = Math.max(0, carbs - carbsAbsorbed);
    //console.error(mealCOB);

    return {
        carbs: Math.round( carbs * 1000 ) / 1000,
        boluses: Math.round( boluses * 1000 ) / 1000,
        // for display only: not usable in calculations
        mealCOB: Math.round( mealCOB )
    };
}

exports = module.exports = diaCarbs;

