var tz = require('timezone');

function diaCarbs(opts, time) {
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    var carbs = 0;
    var boluses = 0;
    var carbDelay = 20 * 60 * 1000;
    //TODO: make this configurable
    var carbs_hr = 30;
    var firstCarbTime = time.getTime();
    if (!treatments) return {};

    treatments.forEach(function(treatment) {
        now = time.getTime();
        var dia_ago = now - profile_data.dia*60*60*1000;
        t = new Date(tz(treatment.timestamp)).getTime();
        if(t > dia_ago && t <= now) {
            if (treatment.carbs >= 1) {
                if (t < firstCarbTime) {
                    //firstCarbTime = treatment.timestamp;
                    firstCarbTime = t;
                    //console.error(firstCarbTime);
                }
                carbs += parseFloat(treatment.carbs);
            }
            if (treatment.bolus >= 0.1) {
                boluses += parseFloat(treatment.bolus);
            }
        }
    });
    now = new Date().getTime();
    hours = (now-firstCarbTime-carbDelay)/(60*60*1000);
    decayed = carbs_hr*hours;
    //console.error(hours, decayed);
    var mealCOB = Math.max(0, carbs - (carbs_hr*hours));
    //console.error(mealCOB);

    return {
        carbs: Math.round( carbs * 1000 ) / 1000,
        boluses: Math.round( boluses * 1000 ) / 1000,
        // for display only: not usable in calculations
        mealCOB: Math.round( mealCOB )
    };
}

exports = module.exports = diaCarbs;

