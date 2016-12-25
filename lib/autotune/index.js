
//var tz = require('timezone');
//var find_meals = require('oref0/lib/meal/history');
//var sum = require('./total');

function generate (inputs) {

    var previous_autotune = inputs.previous_autotune;
    var basalprofile = previous_autotune.basalprofile;
    //console.error(basalprofile);
    var isf_profile = previous_autotune.isfProfile;
    //console.error(isf_profile);
    var isf = isf_profile.sensitivities[0].sensitivity;
    //console.error(isf);
    var carb_ratio = previous_autotune.carb_ratio;
    //console.error(carb_ratio);
    var csf = isf / carb_ratio;
    //console.error(csf);
    var prepped_glucose = inputs.prepped_glucose;
    var csf_glucose = prepped_glucose.csf_glucose_data;
    //console.error(csf_glucose[0]);
    var isf_glucose = prepped_glucose.isf_glucose_data;
    //console.error(isf_glucose[0]);
    var basal_glucose = prepped_glucose.basal_glucose_data;
    //console.error(basal_glucose[0]);

    // convert the basal profile to hourly if it isn't already
    hourlybasalprofile = [];
    for (var i=0; i < 24; i++) {
        for (var j=0; j < basalprofile.length; ++j) {
            if (basalprofile[j].minutes <= i * 60) {
                hourlybasalprofile[i] = JSON.parse(JSON.stringify(basalprofile[j]));
            }
        }
        hourlybasalprofile[i].i=i;
        hourlybasalprofile[i].minutes=i*60;
        hourlybasalprofile[i].rate=Math.round(hourlybasalprofile[i].rate*1000)/1000
    }
    //console.error(hourlybasalprofile);

    // look at net deviations for each hour
    for (var hour=0; hour < 24; hour++) {
        var deviations = 0;
        for (var i=0; i < basal_glucose.length; ++i) {
            //console.error(basal_glucose[i].dateString);
            splitString = basal_glucose[i].dateString.split("T");
            timeString = splitString[1];
            splitTime = timeString.split(":");
            myHour = parseInt(splitTime[0]);
            if (hour == myHour) {
                //console.error(basal_glucose[i].deviation);
                deviations += parseFloat(basal_glucose[i].deviation);
            }
        }
        deviations = Math.round( deviations * 1000 ) / 1000
        //console.error("Hour",hour.toString(),"total deviations:",deviations,"mg/dL");
        // calculate how much less or additional basal insulin would have been required to eliminate the deviations
        basalNeeded = deviations / isf;
        basalNeeded = Math.round( basalNeeded * 1000 ) / 1000
        //console.error("Hour",hour,"basal adjustment needed:",basalNeeded,"U/hr");
        for (var offset=-3; offset < 0; offset++) {
            offsetHour = hour + offset;
            if (offsetHour < 0) { offsetHour += 24; }
            //console.error(offsetHour);
            // adjust the 2h-prior basal by 5% of the needed adjustment
            if (offset == -2) {
                hourlybasalprofile[offsetHour].rate += basalNeeded * .05;
                hourlybasalprofile[offsetHour].rate=Math.round(hourlybasalprofile[offsetHour].rate*1000)/1000
            // and the 1h- and 3h-prior basals by 2.5%
            } else {
                hourlybasalprofile[offsetHour].rate += basalNeeded * .025;
                hourlybasalprofile[offsetHour].rate=Math.round(hourlybasalprofile[offsetHour].rate*1000)/1000
            }
        }
    }
    console.error(hourlybasalprofile);
    basalprofile = hourlybasalprofile;

    // calculate median deviation and bgi in data attributable to ISF
    var deviations = [];
    var bgis = [];
    var avgDeltas = [];
    var ratios = [];
    var count = 0;
    for (var i=0; i < isf_glucose.length; ++i) {
       deviation = parseFloat(isf_glucose[i].deviation);
       deviations.push(deviation);
       bgi = parseFloat(isf_glucose[i].bgi);
       bgis.push(bgi);
       avgDelta = parseFloat(isf_glucose[i].avgDelta);
       avgDeltas.push(avgDelta);
       ratio = 1 + deviation / bgi;
       //console.error("Deviation:",deviation,"BGI:",bgi,"avgDelta:",avgDelta,"ratio:",ratio);
       ratios.push(ratio);
       count++;
    }
    avgDeltas.sort(function(a, b){return a-b});
    bgis.sort(function(a, b){return a-b});
    deviations.sort(function(a, b){return a-b});
    ratios.sort(function(a, b){return a-b});
    p50deviation = percentile(deviations, 0.50);
    p50bgi = percentile(bgis, 0.50);
    p50ratios = Math.round( percentile(ratios, 0.50) * 1000)/1000;

    // calculate what adjustments to ISF would have been necessary to bring median deviation to zero
    fullNewISF = isf * p50ratios;
    fullNewISF = Math.round( fullNewISF * 1000 ) / 1000;
    // and apply 10% of that adjustment
    newIsf = ( 0.9 * isf ) + ( 0.1 * fullNewISF );
    newIsf = Math.round( newIsf * 1000 ) / 1000;
    //console.error(avgRatio);
    //console.error(newIsf);
    console.error("p50deviation:",p50deviation,"p50bgi",p50bgi,"p50ratios:",p50ratios,"Old ISF:",isf,"fullNewISF:",fullNewISF,"newIsf:",newIsf);

    isf = newIsf;

    // calculate net deviations while carbs are absorbing
    // measured from carb entry until COB and deviations both drop to zero

    var deviations = 0;
    var mealCarbs = 0;
    var totalMealCarbs = 0;
    var totalCSFRise = 0;
    var totalDeviations = 0;
    //console.error(csf_glucose[0].mealAbsorption);
    //console.error(csf_glucose[0]);
    for (var i=0; i < csf_glucose.length; ++i) {
        //console.error(csf_glucose[i].mealAbsorption, i);
        if ( csf_glucose[i].mealAbsorption === "start" ) {
            deviations = 0;
            mealCarbs = parseInt(csf_glucose[i].mealCarbs);
        } else if (csf_glucose[i].mealAbsorption === "end") {
            deviations += parseFloat(csf_glucose[i].deviation);
            // compare the sum of deviations from start to end vs. current CSF * mealCarbs
            //console.error(csf,mealCarbs);
            csfRise = csf * mealCarbs;
            //console.error(deviations,isf);
            console.error("csfRise:",csfRise,"deviations:",deviations);
            //totalCSFRise += csfRise;
            totalMealCarbs += mealCarbs;
            totalDeviations += deviations;

        } else {
            deviations += Math.max(0*previous_autotune.min_5m_carbimpact,parseFloat(csf_glucose[i].deviation));
            mealCarbs = Math.max(mealCarbs, parseInt(csf_glucose[i].mealCarbs));
        }
    }
    if (totalMealCarbs == 0) { totalMealCarbs += mealCarbs; }
    if (totalDeviations == 0) { totalDeviations += deviations; }
    //console.error(totalDeviations, totalMealCarbs);
    if (totalMealCarbs == 0) {
        fullNewCSF = csf;
    } else {
        fullNewCSF = Math.round( (totalDeviations / totalMealCarbs)*100 )/100;
    }
    newCsf = ( 0.9 * csf ) + ( 0.1 * fullNewCSF );
    newCsf = Math.round( newCsf * 1000 ) / 1000;
    console.error("totalMealCarbs:",totalMealCarbs,"totalDeviations:",totalDeviations,"fullNewCSF:",fullNewCSF,"newCsf:",newCsf);
    csf = newCsf;

    // reconstruct updated version of previous_autotune as autotune_output
    autotune_output = previous_autotune;
    autotune_output.basalprofile = basalprofile;
    isf_profile.sensitivities[0].sensitivity = isf;
    autotune_output.isfProfile = isf_profile;
    autotune_output.csf = csf;
    carb_ratio = isf / csf;
    autotune_output.carb_ratio = carb_ratio;

    return autotune_output;
}

exports = module.exports = generate;

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
