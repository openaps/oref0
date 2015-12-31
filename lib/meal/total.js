var tz = require('timezone');

function diaCarbs(opts, time) {
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    var carbs = 0;
    var boluses = 0;
    if (!treatments) return {};

    treatments.forEach(function(treatment) {
        now = time.getTime();
        var dia_ago = now - profile_data.dia*60*60*1000;
        t = new Date(tz(treatment.timestamp)).getTime();
        if(t > dia_ago && t <= now) {
            if (treatment.carbs >= 1) {
                carbs += parseFloat(treatment.carbs);
            }
            if (treatment.bolus >= 0.1) {
                boluses += parseFloat(treatment.bolus);
            }
        }
    });

    return {
        carbs: Math.round( carbs * 1000 ) / 1000,
        boluses: Math.round( boluses * 1000 ) / 1000
    };
}

exports = module.exports = diaCarbs;

