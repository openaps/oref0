var _ = require('lodash');

function iobCalc(treatment, time, curve, dia, peak, profile) {

    if (!treatment.insulin) return {};

    if (curve == 'bilinear') {
        return iobCalcBiLinear(treatment, time, dia);
    } else {
        return iobCalcExponential(treatment, time, dia, peak, profile);
    }
}


function iobCalcExponential(treatment, time, dia, peak, profile) {

    var end = dia * 60;  // end of insulin activity, in minutes
 
    if (profile.useCustomPeakTime && profile.insulinPeakTime !== undefined) {
        if (profile.insulinPeakTime < 35 || profile.insulinPeakTime > 120) {
            console.error('Insulin Peak Time is only supported for values between 35 to 120 minutes');
        } else {
            peak = profile.insulinPeakTime;
        }
    }

    if (typeof time === 'undefined') {
        time = new Date();
    }

    var bolusTime = new Date(treatment.date);
    var t = Math.round((time - bolusTime) / 1000 / 60);

    var activityContrib = 0;
    var iobContrib = 0;

    if (t < end) {
        var tau = peak * (1 - peak / end) / (1 - 2 * peak / end);
        var a = 2 * tau / end;
        var S = 1 / (1 - a + (1 + a) * Math.exp(-end / tau));

        activityContrib = treatment.insulin * (S / Math.pow(tau, 2)) * t * (1 - t / end) * Math.exp(-t / tau);
        iobContrib = treatment.insulin * (1 - S * (1 - a) * ((Math.pow(t, 2) / (tau * end * (1 - a)) - t / tau - 1) * Math.exp(-t / tau) + 1));
        //console.error('DIA: ' + dia + ' t: ' + t + ' end: ' + end + ' peak: ' + peak + ' tau: ' + tau + ' a: ' + a + ' S: ' + S + ' activityContrib: ' + activityContrib + ' iobContrib: ' + iobContrib);
    }

    var results = {
        iobContrib: iobContrib,
        activityContrib: activityContrib,
    };

    return results;
}


function iobCalcBiLinear(treatment, time, dia) {

    var diaratio = 3.0 / dia;
    var peak = 75;
    var end = 180;
    if (typeof time === 'undefined') {
        time = new Date();
    }

    var bolusTime = new Date(treatment.date);
    var minAgo = diaratio * Math.round((time - bolusTime) / 1000 / 60);
    var iobContrib = 0;
    var activityContrib = 0;

    if (minAgo < peak) {
        var x1 = (minAgo / 5 + 1);  // minutes since bolus, pre-peak; divided by 5 to work with coefficient estimates
        iobContrib = treatment.insulin * ( (-0.001852*x1*x1) + (0.001852*x1) + 1.000000 );
        activityContrib = treatment.insulin * (2 / dia / 60 / peak) * minAgo;
    } else if (minAgo < end) {
        var x2 = (minAgo - peak) / 5;  // minutes since bolus, post-peak; divided by 5 to work with coefficient estimates
        iobContrib = treatment.insulin * ( (0.001323*x2*x2) + (-0.054233*x2) + 0.555560 );
        activityContrib = treatment.insulin * (2 / dia / 60 - (minAgo - peak) * 2 / dia / 60 / (60 * 3 - peak));
    }

    var results = {
        iobContrib: iobContrib,
        activityContrib: activityContrib
    };

    return results;
}


exports = module.exports = iobCalc;
