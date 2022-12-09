'use strict';

var tz = require('moment-timezone');
var find_insulin = require('./history');
var calculate = require('./calculate');
var sum = require('./total');

function generate (inputs, currentIOBOnly, treatments) {

    if (!treatments) {
        var treatments = find_insulin(inputs);
        // calculate IOB based on continuous future zero temping as well
        var treatmentsWithZeroTemp = find_insulin(inputs, 240);
    } else {
        var treatmentsWithZeroTemp = [];
    }
    //console.error(treatments.length, treatmentsWithZeroTemp.length);
    //console.error(treatments[treatments.length-1], treatmentsWithZeroTemp[treatmentsWithZeroTemp.length-1])

    // Determine peak, curve, and DIA values once and put them in opts to be consumed by ./total
    var profile_data = inputs.profile

    var curveDefaults = {
        'bilinear': {
            requireLongDia: false,
            peak: 75 // not really used, but prevents having to check later
        },
        'rapid-acting': {
            requireLongDia: true,
            peak: 75,
            tdMin: 300
        },
        'ultra-rapid': {
            requireLongDia: true,
            peak: 55,
            tdMin: 300
        },
    };

    var curve = "rapid-acting"; // start as 'rapid-acting'
    var dia = profile_data.dia;
    var peak = 0;

    if (profile_data.curve !== undefined) {
        curve = profile_data.curve.toLowerCase(); // replace it with profile value, if it exists
    }

    if (!(curve in curveDefaults)) { // check that the profile value is one of three expected values, else put it back to 'rapid-acting'
        console.error('Unsupported curve function: "' + curve + '". Supported curves: "bilinear", "rapid-acting" (Novolog, Novorapid, Humalog, Apidra) and "ultra-rapid" (Fiasp, Lyumjev). Defaulting to "rapid-acting".');
        curve = 'rapid-acting';
    }

    var defaults = curveDefaults[curve];

    // force minimum DIA of 3h
    if (dia < 3) {
        console.error("Warning: adjusting DIA from",dia,"to minimum of 3 hours for bilinear curve");
        dia = 3;
    }

    // Force minimum of 5 hour DIA when default requires a Long DIA.
    if (defaults.requireLongDia && dia < 5) {
        console.error("Warning: adjusting DIA from",dia,"to minimum of 5 hours for non-bilinear curve");
        dia = 5;
    }

    // Use custom insulinPeakTime, if value is sensible
    if ( curve === "rapid-acting" ) {
        if (profile_data.useCustomPeakTime === true && profile_data.insulinPeakTime !== undefined) {
            if ( profile_data.insulinPeakTime > 120 ) {
                console.error("Warning: adjusting insulin peak time from",profile_data.insulinPeakTime,"to a maximum of 120m for",profile_data.curve,"insulin");
                peak = 120;
            } else if ( profile_data.insulinPeakTime < 50 ) {
                console.error("Warning: adjusting insulin peak time from",profile_data.insulinPeakTime,"to a minimum of 50m for",profile_data.curve,"insulin");
                peak = 50;
            } else {
                peak = profile_data.insulinPeakTime;
            }
        } else {
            peak = curveDefaults[curve].peak;
        }
    } else if ( curve === "ultra-rapid" ) {
        if (profile_data.useCustomPeakTime === true && profile_data.insulinPeakTime !== undefined) {
            if ( profile_data.insulinPeakTime > 100 ) {
                console.error("Warning: adjusting insulin peak time from",profile_data.insulinPeakTime,"to a maximum of 100m for",profile_data.curve,"insulin");
                peak = 100;
            } else if ( profile_data.insulinPeakTime < 35 ) {
                console.error("Warning: adjusting insulin peak time from",profile_data.insulinPeakTime,"to a minimum of 30m for",profile_data.curve,"insulin");
                peak = 35;
            } else {
                peak = profile_data.insulinPeakTime;
            }
        }
        else {
            peak = curveDefaults[curve].peak;
        }
    } // any other curve (e.g., bilinear) does not use 'peak'

    var opts = {
        treatments: treatments,
        calculate: calculate,
        peak: peak,
        curve: curve,
        dia: dia,
    };

    var optsWithZeroTemp = opts;
    optsWithZeroTemp.treatments = treatmentsWithZeroTemp;

    if ( inputs.autosens ) {
        opts.autosens = inputs.autosens;
    }

    var iobArray = [];
    //console.error(inputs.clock);
    if (! /(Z|[+-][0-2][0-9]:?[034][05])+/.test(inputs.clock) ) {
        console.error("Warning: clock input " + inputs.clock + " is unzoned; please pass clock-zoned.json instead");
    }
    var clock = new Date(tz(inputs.clock));

    var lastBolusTime = new Date(0).getTime(); //clock.getTime());
    var lastTemp = {};
    lastTemp.date = new Date(0).getTime(); //clock.getTime());
    //console.error(treatments[treatments.length-1]);
    treatments.forEach(function(treatment) {
        if (treatment.insulin && treatment.started_at) {
            lastBolusTime = Math.max(lastBolusTime,treatment.started_at);
            //console.error(treatment.insulin,treatment.started_at,lastBolusTime);
        } else if (typeof(treatment.rate) === 'number' && treatment.duration ) {
            if ( treatment.date > lastTemp.date ) {
                lastTemp = treatment;
                lastTemp.duration = Math.round(lastTemp.duration*100)/100;
            }

            //console.error(treatment.rate, treatment.duration, treatment.started_at,lastTemp.started_at)
        }
        //console.error(treatment.rate, treatment.duration, treatment.started_at,lastTemp.started_at)
        //if (treatment.insulin && treatment.started_at) { console.error(treatment.insulin,treatment.started_at,lastBolusTime); }
    });
    var iStop;
    if (currentIOBOnly) {
        // for COB calculation, we only need the zeroth element of iobArray
        iStop=1
    } else {
        // predict IOB out to 4h, regardless of DIA
        iStop=4*60;
    }
    for (var i=0; i<iStop; i+=5){
        var t = new Date(clock.getTime() + i*60000);
        //console.error(t);
        var iob = sum(opts, t);
        var iobWithZeroTemp = sum(optsWithZeroTemp, t);
        //console.error(opts.treatments[opts.treatments.length-1], optsWithZeroTemp.treatments[optsWithZeroTemp.treatments.length-1])
        iobArray.push(iob);
        //console.error(iob.iob, iobWithZeroTemp.iob);
        //console.error(iobArray.length-1, iobArray[iobArray.length-1]);
        iobArray[iobArray.length-1].iobWithZeroTemp = iobWithZeroTemp;
    }
    //console.error(lastBolusTime);
    iobArray[0].lastBolusTime = lastBolusTime;
    iobArray[0].lastTemp = lastTemp;
    return iobArray;
}

exports = module.exports = generate;
