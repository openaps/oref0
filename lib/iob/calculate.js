'use strict';

function iobCalc(treatment, time, curve, dia, peak) {
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


        if (curve === 'bilinear') {
            return iobCalcBilinear(treatment, minsAgo, dia);  // no user-specified peak with this model
        } else {
            return iobCalcExponential(treatment, minsAgo, dia, peak);
        }

    } else { // empty return if (treatment.insulin) == False
        return {};
    }    
}


function iobCalcBilinear(treatment, minsAgo, dia) {
    
    var default_dia = 3.0 // assumed duration of insulin activity, in hours
    var peak = 75;        // assumed peak insulin activity, in minutes
    var end = 180;        // assumed end of insulin activity, in minutes

    // Scale minsAgo by the ratio of the default dia / the user's dia 
    // so the calculations for activityContrib and iobContrib work for 
    // other dia values (while using the constants specified above)
    var timeScalar = default_dia / dia; 
    var scaled_minsAgo = timeScalar * minsAgo;


    var activityContrib = 0;  
    var iobContrib = 0;       

    // Calc percent of insulin activity at peak, and slopes up to and down from peak
    // Based on area of triangle, because area under the insulin action "curve" must sum to 1
    // (length * height) / 2 = area of triangle (1), therefore height (activityPeak) = 2 / length (which in this case is dia, in minutes)
    // activityPeak scales based on user's dia even though peak and end remain fixed
    var activityPeak = 2 / (dia * 60)  
    var slopeUp = activityPeak / peak
    var slopeDown = -1 * (activityPeak / (end - peak))

    if (scaled_minsAgo < peak) {

        activityContrib = treatment.insulin * (slopeUp * scaled_minsAgo);

        var x1 = (scaled_minsAgo / 5) + 1;  // scaled minutes since bolus, pre-peak; divided by 5 to work with coefficients estimated based on 5 minute increments
        iobContrib = treatment.insulin * ( (-0.001852*x1*x1) + (0.001852*x1) + 1.000000 );

    } else if (scaled_minsAgo < end) {
        
        var minsPastPeak = scaled_minsAgo - peak
        activityContrib = treatment.insulin * (activityPeak + (slopeDown * minsPastPeak));

        var x2 = ((scaled_minsAgo - peak) / 5);  // scaled minutes past peak; divided by 5 to work with coefficients estimated based on 5 minute increments
        iobContrib = treatment.insulin * ( (0.001323*x2*x2) + (-0.054233*x2) + 0.555560 );
    }

    return {
        activityContrib: activityContrib,
        iobContrib: iobContrib        
    };
}


function iobCalcExponential(treatment, minsAgo, dia, peak) {

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

    return {
        activityContrib: activityContrib,
        iobContrib: iobContrib        
    };
}


exports = module.exports = iobCalc;
