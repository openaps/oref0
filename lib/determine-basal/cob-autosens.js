var basal = require('oref0/lib/profile/basal');
var get_iob = require('oref0/lib/iob');
var isf = require('../profile/isf');

function detectSensitivityandCarbAbsorption(inputs) {

    glucose_data = inputs.glucose_data.map(function prepGlucose (obj) {
        //Support the NS sgv field to avoid having to convert in a custom way
        obj.glucose = obj.glucose || obj.sgv;
        return obj;
    });
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
    var bucketed_data = [];
    bucketed_data[0] = glucose_data[0];
    j=0;
    for (var i=1; i < glucose_data.length; ++i) {
        var bgTime;
        var lastbgTime;
        if (glucose_data[i].display_time) {
            bgTime = new Date(glucose_data[i].display_time.replace('T', ' '));
        } else if (glucose_data[i].dateString) {
            bgTime = new Date(glucose_data[i].dateString);
        } else { console.error("Could not determine BG time"); }
        if (glucose_data[i-1].display_time) {
            lastbgTime = new Date(glucose_data[i-1].display_time.replace('T', ' '));
        } else if (glucose_data[i-1].dateString) {
            lastbgTime = new Date(glucose_data[i-1].dateString);
        } else { console.error("Could not determine last BG time"); }
        if (glucose_data[i].glucose < 39 || glucose_data[i-1].glucose < 39) {
            continue;
        }
        // only consider BGs for 6h before a meal
        if (mealTime) {
            hoursBeforeMeal = (bgTime-mealTime)/(60*60*1000);
                if (hoursBeforeMeal > 6 || hoursBeforeMeal < 0) {
                    continue;
            }
        }
        var elapsed_minutes = (bgTime - lastbgTime)/(60*1000);
        if(Math.abs(elapsed_minutes) > 8) {
            // interpolate missing data points
            lastbg = glucose_data[i-1].glucose;
            elapsed_minutes = Math.abs(elapsed_minutes);
            //console.error(elapsed_minutes);
            while(elapsed_minutes > 5) {
                nextbgTime = new Date(lastbgTime.getTime() + 5 * 60*1000);
                j++;
                bucketed_data[j] = [];
                bucketed_data[j].date = nextbgTime.getTime();
                gapDelta = glucose_data[i].glucose - lastbg;
                //console.error(gapDelta, lastbg, elapsed_minutes);
                nextbg = lastbg + (5/elapsed_minutes * gapDelta);
                bucketed_data[j].glucose = Math.round(nextbg);
                //console.error("Interpolated", bucketed_data[j]);

                elapsed_minutes = elapsed_minutes - 5;
                lastbg = nextbg;
                lastbgTime = new Date(nextbgTime);
            }

        } else if(Math.abs(elapsed_minutes) > 2) {
            j++;
            bucketed_data[j]=glucose_data[i];
            bucketed_data[j].date = bgTime.getTime();
        } else {
            bucketed_data[j].glucose = (bucketed_data[j].glucose + glucose_data[i].glucose)/2;
        }
    }
    //console.error(bucketed_data);
    for (var i=0; i < bucketed_data.length-3; ++i) {
        var bgTime = new Date(bucketed_data[i].date);
        if (inputs.bgTime && bgTime > inputs.bgTime) {
            continue;
        }

        var sens = isf.isfLookup(profile.isfProfile,bgTime);

        //console.error(bgTime , bucketed_data[i].glucose);
        var bg;
        var avgDelta;
        var delta;
        if (typeof(bucketed_data[i].glucose) != 'undefined') {
            bg = bucketed_data[i].glucose;
            if ( bg < 40 || bucketed_data[i+3].glucose < 40) {
                process.stderr.write("!");
                continue;
            }
            avgDelta = (bg - bucketed_data[i+3].glucose)/3;
            delta = (bg - bucketed_data[i+1].glucose);
        } else { console.error("Could not find glucose data"); }

        avgDelta = avgDelta.toFixed(2);
        iob_inputs.clock=bgTime;
        iob_inputs.profile.current_basal = basal.basalLookup(basalprofile, bgTime);
        //console.log(JSON.stringify(iob_inputs.profile));
        var iob = get_iob(iob_inputs)[0];
        //console.log(JSON.stringify(iob));

        var bgi = Math.round(( -iob.activity * sens * 5 )*100)/100;
        bgi = bgi.toFixed(2);
        //console.error(delta);
        deviation = delta-bgi;
        deviation = deviation.toFixed(2);
        //if (deviation < 0 && deviation > -2) { console.error("BG: "+bg+", avgDelta: "+avgDelta+", BGI: "+bgi+", deviation: "+deviation); }

        // Exclude large positive deviations (carb absorption) from autosens
        if (avgDelta-bgi < 6) {
            if ( deviation > 0 ) {
                inputs.mealTime || process.stderr.write("+");
            } else if ( deviation == 0 ) {
                inputs.mealTime || process.stderr.write("=");
            } else {
                inputs.mealTime || process.stderr.write("-");
            }
            avgDeltas.push(avgDelta);
            bgis.push(bgi);
            deviations.push(deviation);
            deviationSum += parseFloat(deviation);
        } else {
            inputs.mealTime || process.stderr.write(">");
            //console.error(bgTime);
        }

        // if bgTime is more recent than mealTime
        if(bgTime > mealTime) {
            // figure out how many carbs that represents
            // but always assume at least 3mg/dL/5m (default) absorption
            ci = Math.max(deviation, profile.min_5m_carbimpact);
            absorbed = ci * profile.carb_ratio / sens;
            // and add that to the running total carbsAbsorbed
            carbsAbsorbed += absorbed;
        }
    }
    //console.error("");
    inputs.mealTime || process.stderr.write(" ");
    //console.log(JSON.stringify(avgDeltas));
    //console.log(JSON.stringify(bgis));
    avgDeltas.sort(function(a, b){return a-b});
    bgis.sort(function(a, b){return a-b});
    deviations.sort(function(a, b){return a-b});
    for (var i=0.9; i > 0.1; i = i - 0.02) {
        //console.error("p="+i.toFixed(2)+": "+percentile(avgDeltas, i).toFixed(2)+", "+percentile(bgis, i).toFixed(2)+", "+percentile(deviations, i).toFixed(2));
        if ( percentile(deviations, (i+0.02)) >= 0 && percentile(deviations, i) < 0 ) {
            //console.error("p="+i.toFixed(2)+": "+percentile(avgDeltas, i).toFixed(2)+", "+percentile(bgis, i).toFixed(2)+", "+percentile(deviations, i).toFixed(2));
            inputs.mealTime || console.error(Math.round(100*i)+"% of non-meal deviations negative (target 45%-50%)");
        }
    }
    pSensitive = percentile(deviations, 0.50);
    pResistant = percentile(deviations, 0.45);

    average = deviationSum / deviations.length;

    //console.error("Mean deviation: "+average.toFixed(2));
    var basalOff = 0;

    if(pSensitive < 0) { // sensitive
        basalOff = pSensitive * (60/5) / profile.sens;
        inputs.mealTime || process.stderr.write("Excess insulin sensitivity detected: ");
    } else if (pResistant > 0) { // resistant
        basalOff = pResistant * (60/5) / profile.sens;
        inputs.mealTime || process.stderr.write("Excess insulin resistance detected: ");
    } else {
        inputs.mealTime || console.error("Sensitivity normal.");
    }
    ratio = 1 + (basalOff / profile.max_daily_basal);

    // don't adjust more than 1.2x by default (set in preferences.json)
    var rawRatio = ratio;
    ratio = Math.max(ratio, profile.autosens_min);
    ratio = Math.min(ratio, profile.autosens_max);

    if (ratio !== rawRatio) {
      inputs.mealTime || console.error('Ratio limited from ' + rawRatio + ' to ' + ratio);
    }

    ratio = Math.round(ratio*100)/100;
    newisf = Math.round(profile.sens / ratio);
    if (ratio != 1) { inputs.mealTime || console.error("ISF adjusted from "+profile.sens+" to "+newisf); }
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

