var tz = require('timezone');

function diaCarbs(opts, time) {
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    var carbs = 0;
    var boluses = 0;
    if (!treatments) return {};

    treatments.forEach(function(treatment) {
        now = time.getTime();
        //console.log("Time:", time)
        //console.log(now);
        //console.log("DIA:", profile_data.dia);
        var dia_ago = now - profile_data.dia*60*60*1000;
        //console.log(dia_ago);
        //console.log(treatment.timestamp);
        t = new Date(tz(treatment.timestamp)).getTime();
        //console.log(t);
        if(t > dia_ago && t <= now) {
            //console.log(treatment);
            if (treatment.carbs >= 1) {
                //console.log(treatment);
                carbs += treatment.carbs;
            }
            if (treatment.bolus >= 0.1) {
                //console.log(treatment);
                boluses += treatment.bolus;
            }
        }
    });

    return {
        carbs: Math.round( carbs * 1000 ) / 1000,
        boluses: Math.round( boluses * 1000 ) / 1000
    };
}

exports = module.exports = diaCarbs;

