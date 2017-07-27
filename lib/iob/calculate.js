
var refTime = new Date();
var prevTime, prevTreatment, prevResult;

// from: https://stackoverflow.com/a/14873282
function erf(x) {
    // save the sign of x
    var sign = (x >= 0) ? 1 : -1;
    x = Math.abs(x);

    // constants
    var a1 = 0.254829592;
    var a2 = -0.284496736;
    var a3 = 1.421413741;
    var a4 = -1.453152027;
    var a5 = 1.061405429;
    var p = 0.3275911;

    // A&S formula 7.1.26
    var t = 1.0 / (1.0 + p * x);
    var y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return sign * y; // erf(-x) = -erf(x);
}

// This is the old bilinear IOB curve model

function iobCalcBiLinear(treatment, time, dia) {
    var diaratio = 3.0 / dia;
    var peak = 75;
    var end = 180;
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

        if (minAgo < peak) {
            var x = (minAgo / 5 + 1);
            iobContrib = treatment.insulin * (1 - 0.001852 * x * x + 0.001852 * x);
            //activityContrib=sens*treatment.insulin*(2/dia/60/peak)*minAgo;
            activityContrib = treatment.insulin * (2 / dia / 60 / peak) * minAgo;
        } else if (minAgo < end) {
            var y = (minAgo - peak) / 5;
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

    if (typeof time === 'undefined') {
        time = refTime;
    }

	// reuse previous result if invoked with same parameters
	if (treatment === prevTreatment && time === prevTime) { return prevResult;}

    var curve = profile.curve;

    if (curve === undefined ||  curve.toLowerCase() == 'bilinear') {
        return iobCalcBiLinear(treatment, time, dia);
    };

    curve = curve.toLowerCase();

    if (curve != 'rapid-acting' && curve != 'ultra-rapid') {
        console.error('Unsupported curve function: "' + curve + '". Supported curves: "bilinear", "rapid-acting" (Novolog, Novorapid, Humalog, Apidra) and "ultra-rapid" (Fiasp).');
        return;
    }

    var usePeakTime = false;

    if (profile.dia !== 5 && profile.insulinPeakTime !== undefined) {
        console.error('Pump DIA must be set to 5 hours if using the Insulin Peak Time setting');

        if (profile.insulinPeakTime < 35 ||  profile.insulinPeakTime > 120) {
            console.error('Insulin Peak Time is only supported for values between 35 to 120 minutes');
        }
        return;
    }

    if (profile.insulinPeakTime !== undefined) {
        usePeakTime = true;
    }

    // default to the published Fiasp DIA
    var diaratio = 5.0 / profile.dia;

    // Normalize AUC if peak time is changed
    var AUCratio = 1.0;

    if (profile.insulinPeakTime !== undefined && curve == 'ultra-rapid') {
        diaratio = 55.0 / Number(profile.insulinPeakTime);
        AUCratio = diaratio;
    }

    if (profile.insulinPeakTime !== undefined && curve == 'rapid-acting') {
        diaratio = 75.0 / Number(profile.insulinPeakTime);
        AUCratio = diaratio;
    }

    var end = 300;

    var results = {};

    if (treatment.insulin) {
        var bolusTime = new Date(treatment.date);
        var minAgo = diaratio * (time - bolusTime) / 1000 / 60;

        // force the IOB to 0 if over 5 hours have passed
        if (((time - bolusTime) / 1000 / 60) >= end) {
            minAgo = end;
        }

        var iobContrib = 0;
        var activityContrib = 0;

        if (minAgo < end) {
            if (curve.toLowerCase() === 'ultra-rapid') {
                iobContrib = treatment.insulin * (((minAgo / 55) + 1) * Math.exp(-(minAgo) / 55));
                activityContrib = (treatment.insulin * (0.000331 * (minAgo * (Math.exp(-(minAgo) / 55))))) * AUCratio;

            } else {
                iobContrib = treatment.insulin * (1 - erf(0.1 * Math.sqrt(2 * minAgo)) +
                    0.00213 * Math.sqrt(minAgo) * (minAgo + 75) * Math.exp(-minAgo / 50));
                activityContrib = (treatment.insulin * ((4.26E-5) * Math.pow(minAgo, 1.5) * Math.exp(-1.5 * minAgo / 75))) * AUCratio;
            }
        }

        results = {
            iobContrib: iobContrib,
            activityContrib: activityContrib
        };
    }
       
   prevTime = time; prevTreatment = treatment; prevResult = results;
        
    return results;
}

exports = module.exports = iobCalc;