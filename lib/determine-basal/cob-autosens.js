var basal = require('oref0/lib/profile/basal');
var get_iob = require('oref0/lib/iob');

function detectSensitivityandCarbAbsorption(inputs) {

    glucose_data = inputs.glucose_data;
    iob_inputs = inputs.iob_inputs;
    basalprofile = inputs.basalprofile;
    profile = inputs.iob_inputs.profile;
    mealTime = new Date(inputs.mealTime);

    //console.error(mealTime);

    var avgDeltas = [];
    var bgis = [];
    var deviations = [];
    var deviationSum = 0;
    var carbsAbsorbed = 0;
    for (var i=0; i < glucose_data.length-3; ++i) {
        //console.log(glucose_data[i]);
        var bgTime;
        if (glucose_data[i].display_time) {
            bgTime = new Date(glucose_data[i].display_time.replace('T', ' '));
        } else if (glucose_data[i].dateString) {
            bgTime = new Date(glucose_data[i].dateString);
        } else { console.error("Could not determine last BG time"); }
        //console.log(bgTime);
        var bg;
        var avgDelta;
        var delta;
        //console.error(typeof(glucose_data[i].sgv));
        if ( typeof(glucose_data[i].sgv) != 'undefined' ) {
            bg = glucose_data[i].sgv;
            if ( bg < 40 || glucose_data[i+3].sgv < 40) {
                process.stderr.write("!");
                continue;
            }
            avgDelta = (bg - glucose_data[i+3].sgv)/3;
            delta = (bg - glucose_data[i+1].sgv);
        } else if (typeof(glucose_data[i].glucose) != 'undefined') {
            bg = glucose_data[i].glucose;
            if ( bg < 40 || glucose_data[i+3].glucose < 40) {
                process.stderr.write("!");
                continue;
            }
            avgDelta = (bg - glucose_data[i+3].glucose)/3;
            delta = (bg - glucose_data[i+1].glucose);
        } else { console.error("Could not find glucose data"); }

        avgDelta = avgDelta.toFixed(2);
        iob_inputs.clock=bgTime;
        iob_inputs.profile.current_basal = basal.basalLookup(basalprofile, bgTime);
        //console.log(JSON.stringify(iob_inputs.profile));
        var iob = get_iob(iob_inputs)[0];
        //console.log(JSON.stringify(iob));

        var bgi = Math.round(( -iob.activity * profile.sens * 5 )*100)/100;
        bgi = bgi.toFixed(2);
        //console.error(delta);
        deviation = delta-bgi;
        deviation = deviation.toFixed(2);
        //if (deviation < 0 && deviation > -2) { console.error("BG: "+bg+", avgDelta: "+avgDelta+", BGI: "+bgi+", deviation: "+deviation); }

        // Exclude large positive deviations (carb absorption) from autosens
        if (avgDelta-bgi < 6) {
            if ( deviation > 0 ) {
                process.stderr.write("+");
            } else if ( deviation == 0 ) {
                process.stderr.write("=");
            } else {
                process.stderr.write("-");
            }
            avgDeltas.push(avgDelta);
            bgis.push(bgi);
            deviations.push(deviation);
            deviationSum += parseFloat(deviation);
        } else {
            process.stderr.write(">");
            //console.error(bgTime);
        }

        // if bgTime is more recent than mealTime
        if(bgTime > mealTime) {
            // figure out how many carbs that represents
            // but always assume at least 3mg/dL/5m absorption
            ci = Math.max(deviation, 3);
            absorbed = ci * profile.carb_ratio / profile.sens;
            // and add that to the running total carbsAbsorbed
            carbsAbsorbed += absorbed;
        }
    }
    //console.error("");
    process.stderr.write(" ");
    //console.log(JSON.stringify(avgDeltas));
    //console.log(JSON.stringify(bgis));
    avgDeltas.sort(function(a, b){return a-b});
    bgis.sort(function(a, b){return a-b});
    deviations.sort(function(a, b){return a-b});
    for (var i=0.9; i > 0.1; i = i - 0.02) {
        if ( percentile(deviations, (i+0.02)) >= 0 && percentile(deviations, i) < 0 ) {
            //console.error("p="+i.toFixed(2)+": "+percentile(avgDeltas, i).toFixed(2)+", "+percentile(bgis, i).toFixed(2)+", "+percentile(deviations, i).toFixed(2));
            console.error(Math.round(100*i)+"% of non-meal deviations negative (target 45%-50%)");
        }
    }
    pSensitive = percentile(deviations, 0.50);
    pResistant = percentile(deviations, 0.45);
    //p30 = percentile(deviations, 0.3);

    average = deviationSum / deviations.length;

    //console.error("Mean deviation: "+average.toFixed(2));
    var basalOff = 0;

    if(pSensitive < 0) { // sensitive
        basalOff = pSensitive * (60/5) / profile.sens;
        process.stderr.write("Excess insulin sensitivity detected: ");
    } else if (pResistant > 0) { // resistant
        basalOff = pResistant * (60/5) / profile.sens;
        process.stderr.write("Excess insulin resistance detected: ");
    } else {
        console.error("Sensitivity normal.");
    }
    ratio = 1 + (basalOff / profile.max_daily_basal);

    // don't adjust more than 2x
    ratio = Math.max(ratio, 0.5);
    ratio = Math.min(ratio, 2);

    ratio = Math.round(ratio*100)/100;
    newisf = Math.round(profile.sens / ratio);
    if (ratio != 1) { console.error("ISF adjusted from "+profile.sens+" to "+newisf); }
    //console.error("Basal adjustment "+basalOff.toFixed(2)+"U/hr");
    //console.error("Ratio: "+ratio*100+"%: new ISF: "+newisf.toFixed(1)+"mg/dL/U");
    var output = {
        "ratio": ratio
    ,   "carbsAbsorbed": carbsAbsorbed
    }
    return output;
}
module.exports = detectSensitivityandCarbAbsorption;

// From https://gist.github.com/IceCreamYou/6ffa1b18c4c8f6aeaad2
// Returns the value at a given percentile in a sorted numeric array.
// "Linear interpolation between closest ranks" method
function percentile(arr, p) {
    if (arr.length === 0) return 0;
    if (typeof p !== 'number') throw new TypeError('p must be a number');
    if (p <= 0) return arr[0];
    if (p >= 1) return arr[arr.length - 1];

    var index = arr.length * p,
        lower = Math.floor(index),
        upper = lower + 1,
        weight = index % 1;

    if (upper >= arr.length) return arr[lower];
    return arr[lower] * (1 - weight) + arr[upper] * weight;
}

// Returns the percentile of the given value in a sorted numeric array.
function percentRank(arr, v) {
    if (typeof v !== 'number') throw new TypeError('v must be a number');
    for (var i = 0, l = arr.length; i < l; i++) {
        if (v <= arr[i]) {
            while (i < l && v === arr[i]) i++;
            if (i === 0) return 0;
            if (v !== arr[i-1]) {
                i += (v - arr[i-1]) / (arr[i] - arr[i-1]);
            }
            return i / l;
        }
    }
    return 1;
}

