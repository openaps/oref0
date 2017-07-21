
// from: https://stackoverflow.com/a/14873282
function erf(x) {
    // save the sign of x
    var sign = (x >= 0) ? 1 : -1;
    x = Math.abs(x);

    // constants
    var a1 =  0.254829592;
    var a2 = -0.284496736;
    var a3 =  1.421413741;
    var a4 = -1.453152027;
    var a5 =  1.061405429;
    var p  =  0.3275911;

    // A&S formula 7.1.26
    var t = 1.0/(1.0 + p*x);
    var y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return sign * y; // erf(-x) = -erf(x);
}

function iobCalc(treatment, time, dia, curve) {
    if (curve === undefined)
        curve = 'novorapid';   
        
    var diaratio =  5.0 / dia;
    var end = 300;
    //var sens = profile_data.sens;
    if (typeof time === 'undefined') {
        time = new Date();
    }

    var results = {};

    if (treatment.insulin) {
        var bolusTime = new Date(treatment.date);
        var minAgo = diaratio * (time - bolusTime) / 1000 / 60;
        var iobContrib = 0;
        var activityContrib = 0;

        if (minAgo < end) {
            //  (t/55+1)*exp(-t/55) Fiasp
            // 1-erf(0.1sqrt(2t))+0.00213sqrt(t)(t+75)*(exp(-t/50))

            if (curve.toLowerCase() === 'fiasp') {
                iobContrib = treatment.insulin * (((minAgo / 55) + 1) * Math.exp(-(minAgo) / 55));
                activityContrib = treatment.insulin * ( 0.000331 * (minAgo * (Math.exp(-(minAgo) / 55))));
            } else {
                iobContrib = treatment.insulin * ( 1 - erf(0.1 * Math.sqrt(2 * minAgo)) +
                    0.00213 * Math.sqrt(minAgo) * (minAgo + 75) * Math.exp(-minAgo / 50));
                activityContrib = treatment.insulin * ((4.26E-5) * Math.pow(minAgo, 1.5) * Math.exp(-1.5 * minAgo / 75))
            }
        }

        results = {
            iobContrib: iobContrib,
            activityContrib: activityContrib
        };
    }
    return results;
}

exports = module.exports = iobCalc;