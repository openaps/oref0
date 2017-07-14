var tz = require('moment-timezone');
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

    // this sorts the treatments collection in order.
    treatments.sort(function (a, b) {
        var aDate = new Date(tz(a.timestamp));
        var bDate = new Date(tz(b.timestamp));
        //console.error(aDate);
        return bDate.getTime() - aDate.getTime();
    });

    treatments.forEach(function(treatment) {
        var now = time.getTime();
        // consider carbs from up to 6 hours ago in calculating COB
        var carbWindow = now - 6 * 60*60*1000;
        var treatmentDate = new Date(tz(treatment.timestamp));
        var treatmentTime = treatmentDate.getTime();
        if (treatmentTime > carbWindow && treatmentTime <= now) {
            if (treatment.carbs >= 1) {
                //console.error(treatment.carbs, maxCarbs, treatmentDate);
                carbs += parseFloat(treatment.carbs);
                COB_inputs.mealTime = treatmentTime;
                var myCarbsAbsorbed = calcMealCOB(COB_inputs).carbsAbsorbed;
                var myMealCOB = Math.max(0, carbs - myCarbsAbsorbed);
                mealCOB = Math.max(mealCOB, myMealCOB);
                //console.error("COB:",mealCOB);
            }
            if (treatment.bolus >= 0.1) {
                boluses += parseFloat(treatment.bolus);
            }
        }
    });

    // calculate the current deviation and steepest deviation downslope over the last hour
    COB_inputs.ciTime = time.getTime();
    // set mealTime to 6h ago for Deviation calculations
    COB_inputs.mealTime = time.getTime() - 6 * 60 * 60 * 1000;
    var c = calcMealCOB(COB_inputs);
    //console.error(c.currentDeviation, c.minDeviationSlope);

    // set a hard upper limit on COB to mitigate impact of erroneous or malicious carb entry
    mealCOB = Math.min( profile.maxCOB, mealCOB );

    return {
        carbs: Math.round( carbs * 1000 ) / 1000
    ,   boluses: Math.round( boluses * 1000 ) / 1000
    ,   mealCOB: Math.round( mealCOB )
    ,   currentDeviation: Math.round( c.currentDeviation * 100 ) / 100
    ,   maxDeviation: Math.round( c.maxDeviation * 100 ) / 100
    ,   minDeviationSlope: Math.round( c.minDeviationSlope * 1000 ) / 1000
    };
}

exports = module.exports = diaCarbs;

