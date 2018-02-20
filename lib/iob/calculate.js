var _ = require('lodash');

function iobCalc(treatment, time, curve, dia, peak, profile) {

    if (treatment.insulin) {

        // Calc minutes since bolus (minsAgo)
        if (typeof time === 'undefined') {
            time = new Date();
        }
        var bolusTime = new Date(treatment.date);
        var minsAgo = Math.round((time - bolusTime) / 1000 / 60);


        if (curve == 'bilinear') {
            return iobCalcBiLinear(treatment, minsAgo, dia);
        } else {
            return iobCalcExponential(treatment, minsAgo, dia, peak, profile);
        }

    } else { // empty return if (treatment.insulin) == False
        return {};
    }    
}


function iobCalcBiLinear(treatment, minsAgo, dia) {
    
    var timeScalar = 3.0 / dia;
    var peak = 75;  // peak insulin activity, in minutes
    var end = 180;  // end of insulin activity, in minutes

    var scaled_minsAgo = timeScalar * minsAgo;

    var activityContrib = 0;  // insulin used in last minute
    var iobContrib = 0;       // insulin still on board

    if (scaled_minsAgo < peak) {
        activityContrib = treatment.insulin * (2 / dia / 60 / peak) * scaled_minsAgo;

        var x1 = (scaled_minsAgo / 5 + 1);  // minutes since bolus, pre-peak; divided by 5 to work with coefficient estimates
        iobContrib = treatment.insulin * ( (-0.001852*x1*x1) + (0.001852*x1) + 1.000000 );

    } else if (scaled_minsAgo < end) {
        activityContrib = treatment.insulin * (2 / dia / 60 - (scaled_minsAgo - peak) * 2 / dia / 60 / (end - peak));

        var x2 = (scaled_minsAgo - peak) / 5;  // minutes since bolus, post-peak; divided by 5 to work with coefficient estimates
        iobContrib = treatment.insulin * ( (0.001323*x2*x2) + (-0.054233*x2) + 0.555560 );
    }

    var results = {
        activityContrib: activityContrib,
        iobContrib: iobContrib        
    };

    return results;
}


function iobCalcExponential(treatment, minsAgo, dia, peak, profile) {

    var end = dia * 60;  // end of insulin activity, in minutes
 
    // Use custom peak time if values are valid
    if (profile.useCustomPeakTime && profile.insulinPeakTime !== undefined) {
        if (profile.insulinPeakTime > 35 && profile.insulinPeakTime < 120) {
            peak = profile.insulinPeakTime;
        } else {
            console.error('Insulin Peak Time is only supported for values between 35 to 120 minutes');
        }
    }

    var activityContrib = 0;  // insulin used in last minute
    var iobContrib = 0;       // insulin still on board

    if (minsAgo < end) {
        var tau = peak * (1 - peak / end) / (1 - 2 * peak / end);
        var a = 2 * tau / end;
        var S = 1 / (1 - a + (1 + a) * Math.exp(-end / tau));

        activityContrib = treatment.insulin * (S / Math.pow(tau, 2)) * minsAgo * (1 - minsAgo / end) * Math.exp(-minsAgo / tau);
        iobContrib = treatment.insulin * (1 - S * (1 - a) * ((Math.pow(minsAgo, 2) / (tau * end * (1 - a)) - minsAgo / tau - 1) * Math.exp(-minsAgo / tau) + 1));
        //console.error('DIA: ' + dia + ' minsAgo: ' + minsAgo + ' end: ' + end + ' peak: ' + peak + ' tau: ' + tau + ' a: ' + a + ' S: ' + S + ' activityContrib: ' + activityContrib + ' iobContrib: ' + iobContrib);
    }

    var results = {
        activityContrib: activityContrib,
        iobContrib: iobContrib        
    };

    return results;
}


exports = module.exports = iobCalc;
