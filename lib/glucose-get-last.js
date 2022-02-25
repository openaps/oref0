function getDateFromEntry(entry) {
return entry.date || Date.parse(entry.display_time) || Date.parse(entry.dateString);
}

function round(value, digits)
{
    if (! digits) { digits = 0; }
    var scale = Math.pow(10, digits);
    return Math.round(value * scale) / scale;
}

var getLastGlucose = function (data) {
    data = data.filter(function(obj) {
    return obj.glucose || obj.sgv;
    }).map(function prepGlucose (obj) {
        //Support the NS sgv field to avoid having to convert in a custom way
        obj.glucose = obj.glucose || obj.sgv;
        if ( obj.glucose !== null ) {
            return obj;
        }
    });

    var now = data[0];
    var now_date = getDateFromEntry(now);
    var change;
    var last_deltas = [];
    var short_deltas = [];
    var long_deltas = [];
    var last_cal = 0;

    //console.error(now.glucose);
    for (var i=1; i < data.length; i++) {
        // if we come across a cal record, don't process any older SGVs
        if (typeof data[i] !== 'undefined' && data[i].type === "cal") {
            last_cal = i;
            break;
        }
        // only use data from the same device as the most recent BG data point
        if (typeof data[i] !== 'undefined' && data[i].glucose > 38 && data[i].device === now.device) {
            var then = data[i];
            var then_date = getDateFromEntry(then);
            var avgdelta = 0;
            var minutesago;
            if (typeof then_date !== 'undefined' && typeof now_date !== 'undefined') {
                minutesago = Math.round( (now_date - then_date) / (1000 * 60) );
                // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
                change = now.glucose - then.glucose;
                avgdelta = change/minutesago * 5;
            } else { console.error("Error: date field not found: cannot calculate avgdelta"); }
            //if (i < 5) {
                //console.error(then.glucose, minutesago, avgdelta);
            //}
            // use the average of all data points in the last 2.5m for all further "now" calculations
            if (-2 < minutesago && minutesago < 2.5) {
                now.glucose = ( now.glucose + then.glucose ) / 2;
                now_date = ( now_date + then_date ) / 2;
                //console.error(then.glucose, now.glucose);
            // short_deltas are calculated from everything ~5-15 minutes ago
            } else if (2.5 < minutesago && minutesago < 17.5) {
                //console.error(minutesago, avgdelta);
                short_deltas.push(avgdelta);
                // last_deltas are calculated from everything ~5 minutes ago
                if (2.5 < minutesago && minutesago < 7.5) {
                    last_deltas.push(avgdelta);
                }
                //console.error(then.glucose, minutesago, avgdelta, last_deltas, short_deltas);
            // long_deltas are calculated from everything ~20-40 minutes ago
            } else if (17.5 < minutesago && minutesago < 42.5) {
                long_deltas.push(avgdelta);
            }
        }
    }
    var last_delta = 0;
    var short_avgdelta = 0;
    var long_avgdelta = 0;

    // start autoISF by https://github.com/ga-zelle/autoISF , relevant variables and functions
    // mod 7: append 2 variables for 5% range
    var autoISF_duration = 0;
    var autoISF_average = 0;
    // mod 8: append 3 variables for deltas based on regression analysis
    var slope05 = 0;
    var slope15 = 0;
    var slope40 = 0;
    // mod 14f: append results from best fitting parabola
    var dura_p = 0;
    var delta_pl = 0;
    var delta_pn = 0;
    var r_squ = 0;
    var bg_acceleration = 0;
    var a_0 = 0;
    var a_1 = 0;
    var a_2 = 0;
    var pp_debug = "autoISF Mod14-Debug: ";

    if (last_deltas.length > 0) {
        last_delta = last_deltas.reduce(function(a, b) { return a + b; }) / last_deltas.length;
    }
    if (short_deltas.length > 0) {
        short_avgdelta = short_deltas.reduce(function(a, b) { return a + b; }) / short_deltas.length;
    }
    if (long_deltas.length > 0) {
        long_avgdelta = long_deltas.reduce(function(a, b) { return a + b; }) / long_deltas.length;
    }
    var bw = 0.05;
    var sumBG = now.glucose;
    var oldavg = now.glucose;
    var minutesdur = 0;
    for (var i = 1; i < data.length; i++) {
        var then = data[i];
        var then_date = getDateFromEntry(then);
    //  mod 7c: stop the series if there was a CGM gap greater than 13 minutes, i.e. 2 regular readings
            if (Math.round((now_date - then_date) / (1000 * 60)) - minutesdur > 13) {
            break;
            }
            if (then.glucose > oldavg*(1-bw) && then.glucose < oldavg*(1+bw)) {
            sumBG += then.glucose;
            oldavg = sumBG / (i+1);
            minutesdur = Math.round((now_date - then_date) / (1000 * 60));
            } else {
            break;
        }
    }
            autoISF_average = oldavg;
            autoISF_duration = minutesdur;

            // mod 8: calculate 3 variables for deltas based on linear regression
            // initially just test the handling of arguments
            var slope05 = 1.05;
            var slope15 = 1.15;
            var slope40 = 1.40;

            // mod 8a: now do the real maths based on
            // http://www.carl-engler-schule.de/culm/culm/culm2/th_messdaten/mdv2/auszug_ausgleichsgerade.pdf
            var sumBG  = 0;         // y
            var sumt   = 0;         // x
            var sumBG2 = 0;         // y^2
            var sumt2  = 0;         // x^2
            var sumxy  = 0;         // x*y
            //double a;
            var b;                   // y = a + b * x
            var level = 7.5;
            var minutesL;
            // here, longer deltas include all values from 0 up the related limit
            for (var i = 0; i < data.length; i++) {
                var then = data[i];
                var then_date = getDateFromEntry(then);
                minutesL = (now_date - then_date) / (1000 * 60);
                // watch out: the scan goes backwards in time, so delta has wrong sign
                if(i * sumt2 == sumt * sumt) {
                    b = 0.0;
                }
                else {
                    b = (i * sumxy - sumt * sumBG) / (i * sumt2 - sumt * sumt);
                }
                if (minutesL > level && level == 7.5) {
                    slope05 = -b * 5;
                    level = 17.5;
                }
                if (minutesL > level && level == 17.5) {
                    slope15 = -b * 5;
                    level = 42.5;
                }
                if (minutesL > level && level == 42.5) {
                    slope40 = -b * 5;
                    break;
                }

                sumt   += minutesL;
                sumt2  += minutesL * minutesL;
                sumBG  += then.glucose;
                sumBG2 += then.glucose * then.glucose;
                sumxy  += then.glucose * minutesL;
            }

            // mod 14f: calculate best parabola and determine delta by extending it 5 minutes into the future
            // nach https://www.codeproject.com/Articles/63170/Least-Squares-Regression-for-Quadratic-Curve-Fitti
            //
            //  y = a2*x^2 + a1*x + a0      or
            //  y = a*x^2  + b*x  + c       respectively

            // initially just test the handling of arguments
            var dura_p  = 0;
            var delta_pl = 0;
            var delta_pn = 0;
            var bg_acceleration = 0;
            var r_squ   = 0;
            var best_a = 0;
            var best_b = 0;
            var best_c = 0;
            var a_0 = 0;
            var a_1 = 0;
            var a_2 = 0;

            if (data.length <= 3) {                      // last 3 points make a trivial parabola
                dura_p  = 0;
                delta_pl = 0;
                delta_pn = 0;
                bg_acceleration = 0;
                r_squ   = 0;
                a_0 = 0;
                a_1 = 0;
                a_2 = 0;
            } else {
                //double corrMin = 0.90;                  // go backwards until the correlation coefficient goes below
                var sy    = 0;                        // y
                var sx    = 0;                        // x
                var sx2   = 0;                        // x^2
                var sx3   = 0;                        // x^3
                var sx4   = 0;                        // x^4
                var sxy   = 0;                        // x*y
                var sx2y  = 0;                        // x^2*y
                var corrMax = 0;
                var iframe = data[0];
                var time_0 = getDateFromEntry(iframe);
                var ti_last = 0;
                //# for best numerical accurarcy time and bg must be of same order of magnitude
                var scaleTime = 300;                  //# in 5m; values are  0, 1, 2, 3, 4, ...
                var scaleBg   =  50;                  //# TIR range is now 1.4 - 3.6

                for (var i = 0; i < data.length; i++) {
                    var then = data[i];
                    var then_date = getDateFromEntry(then);
                    // skip records older than 47.5 minutes
                    var ti = (then_date - time_0) / 1000 / scaleTime;
                    if (-ti *scaleTime > 47 * 60) {                        // skip records older than 47.5 minutes
                        break;
                    } else if (ti < ti_last - 7.5 * 60 / scaleTime) {       // stop scan if a CGM gap > 7.5 minutes is detected
                        if ( i<3) {                             // history too short for fit
                            dura_p =  -ti_last / 60;
                            delta_pl = 0;
                            delta_pn = 0;
                            bg_acceleration= 0;
                            r_squ = 0;
                            a_0 = 0;
                            a_1 = 0;
                            a_2 = 0;
                        }
                        break;
                    }
                    ti_last = ti;
                    var bg = then.glucose/scaleBg;
                    sx += ti;
                    sx2 += Math.pow(ti, 2);
                    sx3 += Math.pow(ti, 3);
                    sx4 += Math.pow(ti, 4);
                    sy  += bg;
                    sxy += ti * bg;
                    sx2y += Math.pow(ti, 2) * bg;
                    var n = i + 1;
                    var D  = 0;
                    var Da = 0;
                    var Db = 0;
                    var Dc = 0;
                    if (n > 3) {
                        D  = sx4 * (sx2 * n - sx * sx) - sx3 * (sx3 * n - sx * sx2) + sx2 * (sx3 * sx - sx2 * sx2);
                        Da = sx2y* (sx2 * n - sx * sx) - sxy * (sx3 * n - sx * sx2) + sy  * (sx3 * sx - sx2 * sx2);
                        Db = sx4 * (sxy * n - sy * sx) - sx3 * (sx2y* n - sy * sx2) + sx2 * (sx2y* sx - sxy * sx2);
                        Dc = sx4 * (sx2 *sy - sx *sxy) - sx3 * (sx3 *sy - sx *sx2y) + sx2 * (sx3 *sxy - sx2 * sx2y);
                    }
                    if (D != 0) {
                        var a = Da / D;
                        b = Db / D;              // b initialised in linear fit !
                        var c = Dc / D;
                        var y_mean = sy / n;
                        var s_squares = 0;
                        var s_residual_squares = 0;
                        for (var j = 0; j <= i; j++) {
                            var before = data[j];
                            var before_date = getDateFromEntry(before);
                            s_squares += Math.pow(before.glucose / scaleBg - y_mean, 2);
                            var delta_t = (before_date - time_0) / 1000 / scaleTime;
                            var bg_j = a * Math.pow(delta_t, 2) + b * delta_t + c;
                            s_residual_squares += Math.pow(before.glucose / scaleBg - bg_j, 2);
                        }
                        var r_squ = 0.64;
                        if (s_squares != 0) {
                            r_squ = 1 - s_residual_squares / s_squares;
                        }
                        if (n > 3) {
                            if (r_squ >= corrMax) {
                                corrMax = r_squ;
                                // double delta_t = (then_date - time_0) / 1000;
                                dura_p = -ti * scaleTime / 60;            // remember we are going backwards in time
                                var delta5Min = 5 * 60 / scaleTime;
                                delta_pl =-scaleBg * (a * Math.pow(- delta5Min, 2) - b * delta5Min);     // 5 minute slope from last fitted bg starting from last bg, i.e. t=0
                                delta_pn = scaleBg * (a * Math.pow( delta5Min, 2) + b * delta5Min);     // 5 minute slope to next fitted bg starting from last bg, i.e. t=0
                                bg_acceleration = 2 * a * scaleBg;             // 2nd derivative of parabola per (5min)^2
                                a_0 = c * scaleBg;
                                a_1 = b * scaleBg;
                                a_2 = a * scaleBg;
                                //r_squ = corrMax;
                                best_a = a * scaleBg;
                                best_b = b * scaleBg;
                                best_c = c * scaleBg;
                            }
                        }
                    }
                }
                pp_debug += "coeffs a/b/c=(" + round(best_a,2) + " / " + round(best_b,2) + " / " + round(best_c,2) + "); bg date=" + time_0 + "; ";
                pp_debug += "Parabola Fits a0/a1/a2=(" + round(a_0,2) + " / " + round(a_1,2) + " / " + round(a_2,2) + "); ";
            }
           pp_debug += "Slopes 05/15/40=(" + round(slope05,2) + " / " + round(slope15,2) + " / " + round(slope40,2) + "); "
    return {
        delta: Math.round( last_delta * 10000 ) / 10000
        , glucose: Math.round( now.glucose * 10000 ) / 10000
        , noise: Math.round(now.noise)
        , short_avgdelta: Math.round( short_avgdelta * 10000 ) / 10000
        , long_avgdelta: Math.round( long_avgdelta * 10000 ) / 10000
        // autoISF values to return to determineBasal.js
        , autoISF_average: Math.round( autoISF_average * 10000) / 10000
        , autoISF_duration: Math.round(autoISF_duration * 10000) / 10000
        , dura_p: Math.round( dura_p * 10000) / 10000
        , delta_pl: Math.round( delta_pl * 10000) / 10000
        , delta_pn: Math.round( delta_pn * 10000) / 10000
        , bg_acceleration: bg_acceleration
        , r_squ: Math.round( corrMax * 10000) / 10000
        , parabola_fit_a0: Math.round( a_0 * 10000) / 10000
        , parabola_fit_a1: Math.round( a_1 * 10000) / 10000
        , parabola_fit_a2: Math.round( a_2 * 10000) / 10000
        , pp_debug
        // end autoISF values
        , date: now_date
        , last_cal: last_cal
        , device: now.device
    };
};

module.exports = getLastGlucose;
