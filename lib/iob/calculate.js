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

// This is the old bilinear IOB curve model

function iobCalcBiLinear(treatment, time, dia) {
    var diaratio = 3.0 / dia;
    var peak = 75 ;
    var end = 180 ;
    //var sens = profile_data.sens;
    if (typeof time === 'undefined') {
        time = new Date();
    }

    var results = {};

    if (treatment.insulin) {
        var bolusTime = new Date(treatment.date);
        var minAgo = diaratio * (time-bolusTime) / 1000 / 60;
        var iobContrib = 0;
        var activityContrib = 0;

        if (minAgo < peak) {
            var x = (minAgo/5 + 1);
            iobContrib = treatment.insulin * (1 - 0.001852 * x * x + 0.001852 * x);
            //activityContrib=sens*treatment.insulin*(2/dia/60/peak)*minAgo;
            activityContrib = treatment.insulin * (2 / dia / 60 / peak) * minAgo;
        } else if (minAgo < end) {
            var y = (minAgo-peak)/5;
            iobContrib = treatment.insulin * (0.001323 * y * y - .054233 * y + .55556);
            //activityContrib=sens*treatment.insulin*(2/dia/60-(minAgo-peak)*2/dia/60/(60*dia-peak));
            activityContrib = treatment.insulin * (2 / dia / 60 - (minAgo - peak) * 2 / dia / 60 / (60 * 3 - peak));
        }

        results = {
            iobContrib: iobContrib,
            activityContrib: activityContrib
        };
    }

    return results;
}


function iobCalc(treatment, time, dia, profile) {

	var curve = profile.curve;

    if (curve === undefined || curve.toLowerCase() == 'bilinear') {
    	return iobCalcBiLinear(treatment, time, dia);
    };
    
    curve = curve.toLowerCase();
    
    if (curve != 'novorapid' && curve != 'fiasp') {
    	console.error('Unsupported curve function: "' + curve + '". Supported curves: bilinear, novorapid and fiasp.');
    }

	if (profile.usePumpDia !== undefined && profile.insulinPeakTime !== undefined) {
		console.error('Defining both peak time and DIA is not supported');
	}

	// default to the published Fiasp DIA
    
    var dia = 5.0;
    if (profile.usePumpDia !== undefined && profile.dia) { dia = profile.dia; }
    var diaratio =  5.0 / dia;

	var iobRatio = 1.0;

	if (profile.insulinPeakTime !== undefined) {
		diaratio = 55 / Number(profile.insulinPeakTime);
		iobRatio = Number(profile.insulinPeakTime) / 55;
	}
    
    var end = 300;

    if (typeof time === 'undefined') {
        time = new Date();
    }

    var results = {};

    if (treatment.insulin) {
        var bolusTime = new Date(treatment.date);
        var minAgo = diaratio * (time - bolusTime) / 1000 / 60;
        var minAgoIOB = iobRatio * (time - bolusTime) / 1000 / 60;
        var iobContrib = 0;
        var activityContrib = 0;

        if (minAgo < end) {
            //  (t/55+1)*exp(-t/55) Fiasp
            // 1-erf(0.1sqrt(2t))+0.00213sqrt(t)(t+75)*(exp(-t/50))

            if (curve.toLowerCase() === 'fiasp') {
                iobContrib = treatment.insulin * (((minAgoIOB / 55) + 1) * Math.exp(-(minAgoIOB) / 55));
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