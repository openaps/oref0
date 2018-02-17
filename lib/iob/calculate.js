var _ = require('lodash');

function iobCalcBiLinear(treatment, time, dia) {
    var diaratio = 3.0 / dia;
    var peak = 75;
    var end = 180;
    if (typeof time === 'undefined') {
        time = new Date();
    }

    var results = {};

    if (treatment.insulin) {
        var bolusTime = new Date(treatment.date);
        var minAgo = diaratio * (time - bolusTime) / 1000 / 60;
        var iobContrib = 0;
        var activityContrib = 0;

        if (minAgo < peak) {
            var x = (minAgo / 5 + 1);
            iobContrib = treatment.insulin * (1.000000 - 0.001852 * x * x + 0.001852 * x);
            activityContrib = treatment.insulin * (2 / dia / 60 / peak) * minAgo;
        } else if (minAgo < end) {
            var y = (minAgo - peak) / 5;
            iobContrib = treatment.insulin * (0.555560 + 0.001323 * y * y - 0.054233 * y);
            activityContrib = treatment.insulin * (2 / dia / 60 - (minAgo - peak) * 2 / dia / 60 / (60 * 3 - peak));
        }

        results = {
            iobContrib: iobContrib,
            activityContrib: activityContrib
        };
    }

    return results;
}


function iobCalc(treatment, time, curve, dia, peak, profile) {

    if (!treatment.insulin) return {};

    if (curve == 'bilinear') {
        return iobCalcBiLinear(treatment, time, dia);
    }

    var td = dia * 60;

    var tp = peak;

    if (profile.useCustomPeakTime && profile.insulinPeakTime !== undefined) {
        if (profile.insulinPeakTime < 35 || profile.insulinPeakTime > 120) {
            console.error('Insulin Peak Time is only supported for values between 35 to 120 minutes');

        } else {
            tp = profile.insulinPeakTime;
        }
    }

    if (typeof time === 'undefined') {
        time = new Date();
    }

    var bolusTime = new Date(treatment.date);
    var t = Math.round((time - bolusTime) / 1000 / 60);

    var activityContrib = 0;
    var iobContrib = 0;

    if (t < td) {

        var tau = tp * (1 - tp / td) / (1 - 2 * tp / td);
        var a = 2 * tau / td;
        var S = 1 / (1 - a + (1 + a) * Math.exp(-td / tau));

        activityContrib = treatment.insulin * (S / Math.pow(tau, 2)) * t * (1 - t / td) * Math.exp(-t / tau);
        iobContrib = treatment.insulin * (1 - S * (1 - a) * ((Math.pow(t, 2) / (tau * td * (1 - a)) - t / tau - 1) * Math.exp(-t / tau) + 1));

        //console.error('DIA: ' + dia + ' t: ' + t + ' td: ' + td + ' tp: ' + tp + ' tau: ' + tau + ' a: ' + a + ' S: ' + S + ' activityContrib: ' + activityContrib + ' iobContrib: ' + iobContrib);

    }

    results = {
        iobContrib: iobContrib,
        activityContrib: activityContrib,
    };

    return results;
}

exports = module.exports = iobCalc;
