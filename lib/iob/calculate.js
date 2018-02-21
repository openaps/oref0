var _ = require('lodash');

function iobCalc(treatment, time, curve, dia, peak, profile) {
    // iobCalc returns two variables:
    //   activityContrib = units of treatment.insulin used in previous minute
    //   iobContrib = units of treatment.insulin still remaining at a given point in time
    // ("Contrib" is used because these are the amounts contributed from pontentially multiple treatment.insulin dosages -- totals are calculated in total.js)
    //
    // Variables can be calculated using either:
    //   A bilinear insulin action curve (which only takes duration of insulin activity (dia) as an input parameter) or
    //   An exponential insulin action curve (which takes both a dia and a peak parameter)
    // (which functional form to use is specified in the user's profile)
    
    if (treatment.insulin) {

        // Calc minutes since bolus (minsAgo)
        if (typeof time === 'undefined') {
            time = new Date();
        }
        var bolusTime = new Date(treatment.date);
        var minsAgo = Math.round((time - bolusTime) / 1000 / 60);


        if (curve == 'bilinear') {
            return iobCalcBilinear(treatment, minsAgo, dia);  // no user-specified peak with this model
        } else {
            return iobCalcExponential(treatment, minsAgo, dia, peak, profile);
        }

    } else { // empty return if (treatment.insulin) == False
        return {};
    }    
}


function iobCalcBilinear(treatment, minsAgo, dia) {
    
    const default_dia = 3.0 // assumed duration of insulin activity, in hours
    const peak = 75;        // assumed peak insulin activity, in minutes
    const end = 180;        // assumed end of insulin activity, in minutes

    // Scale minsAgo by the ratio of the default dia / the user's dia 
    // so the calculations for activityContrib and iobContrib work for 
    // other dia values (while using the constants specified above)
    var timeScalar = default_dia / dia; 
    var scaled_minsAgo = timeScalar * minsAgo;


    var activityContrib = 0;  
    var iobContrib = 0;       

    if (scaled_minsAgo < peak) {
        activityContrib = treatment.insulin * (2 / dia / 60 / peak) * scaled_minsAgo;

        var x1 = (scaled_minsAgo / 5) + 1;  // scaled minutes since bolus, pre-peak; divided by 5 to work with coefficients estimated based on 5 minute increments
        iobContrib = treatment.insulin * ( (-0.001852*x1*x1) + (0.001852*x1) + 1.000000 );

    } else if (scaled_minsAgo < end) {
        activityContrib = treatment.insulin * (2 / dia / 60 - (scaled_minsAgo - peak) * 2 / dia / 60 / (end - peak));

        var x2 = ((scaled_minsAgo - peak) / 5);  // scaled minutes past peak; divided by 5 to work with coefficients estimated based on 5 minute increments
        iobContrib = treatment.insulin * ( (0.001323*x2*x2) + (-0.054233*x2) + 0.555560 );
    }

    var results = {
        activityContrib: activityContrib,
        iobContrib: iobContrib        
    };

    return results;
}


function iobCalcExponential(treatment, minsAgo, dia, peak, profile) {

    // Use custom peak time (in minutes) if value is valid
    if (profile.useCustomPeakTime && profile.insulinPeakTime !== undefined) {
        if (profile.insulinPeakTime > 35 && profile.insulinPeakTime < 120) {
            peak = profile.insulinPeakTime;
        } else {
            console.error('Insulin Peak Time is only supported for values between 35 to 120 minutes');
        }
    }
    var end = dia * 60;  // end of insulin activity, in minutes


    var activityContrib = 0;  
    var iobContrib = 0;       

    if (minsAgo < end) {
        
        // Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
        // Mapping of original source variable names to those used here:
        //   td = end
        //   tp = peak
        //   t  = minsAgo
        var tau = peak * (1 - peak / end) / (1 - 2 * peak / end);  // time constant of exponential decay
        var a = 2 * tau / end;                                     // rise time factor
        var S = 1 / (1 - a + (1 + a) * Math.exp(-end / tau));      // auxiliary scale factor
        
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
