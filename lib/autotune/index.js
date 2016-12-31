// does three things - tunes basals, ISF, and CSF

function tuneAllTheThings (inputs) {

    var previous_autotune = inputs.previous_autotune;
    var pumpprofile = inputs.pumpprofile;
    var pumpbasalprofile = pumpprofile.basalprofile;
    //console.error(pumpbasalprofile);
    var basalprofile = previous_autotune.basalprofile;
    //console.error(basalprofile);
    var isf_profile = previous_autotune.isfProfile;
    //console.error(isf_profile);
    var isf = isf_profile.sensitivities[0].sensitivity;
    //console.error(isf);
    var carb_ratio = previous_autotune.carb_ratio;
    //console.error(carb_ratio);
    var csf = isf / carb_ratio;
    // conditional on there being a pump profile; if not then skip
    if (pumpprofile) { pump_isf_profile = pumpprofile.isfProfile; }
    if (pump_isf_profile && pump_isf_profile.sensitivities[0]) {
        pumpISF = pump_isf_profile.sensitivities[0].sensitivity;
        pump_carb_ratio = pumpprofile.carb_ratio;
        pumpCSF = pumpISF / pump_carb_ratio;
    }
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
    hourlypumpprofile = [];
    for (var i=0; i < 24; i++) {
        // aututuned basal profile
        for (var j=0; j < basalprofile.length; ++j) {
            if (basalprofile[j].minutes <= i * 60) {
                hourlybasalprofile[i] = JSON.parse(JSON.stringify(basalprofile[j]));
            }
        }
        hourlybasalprofile[i].i=i;
        hourlybasalprofile[i].minutes=i*60;
        hourlybasalprofile[i].rate=Math.round(hourlybasalprofile[i].rate*1000)/1000
        // pump basal profile
        if (pumpbasalprofile && pumpbasalprofile[0]) {
            for (var j=0; j < pumpbasalprofile.length; ++j) {
                //console.error(pumpbasalprofile[j]);
                if (pumpbasalprofile[j].minutes <= i * 60) {
                    hourlypumpprofile[i] = JSON.parse(JSON.stringify(pumpbasalprofile[j]));
                }
            }
            hourlypumpprofile[i].i=i;
            hourlypumpprofile[i].minutes=i*60;
            hourlypumpprofile[i].rate=Math.round(hourlypumpprofile[i].rate*1000)/1000
        }
    }
    //console.error(hourlypumpprofile);
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
        // only apply 20% of the needed adjustment to keep things relatively stable
        basalNeeded = 0.2 * deviations / isf;
        basalNeeded = Math.round( basalNeeded * 1000 ) / 1000
        // if basalNeeded is positive, adjust each of the 1-3 hour prior basals by 10% of the needed adjustment
        console.error("Hour",hour,"basal adjustment needed:",basalNeeded,"U/hr");
        if (basalNeeded > 0 ) {
            for (var offset=-3; offset < 0; offset++) {
                offsetHour = hour + offset;
                if (offsetHour < 0) { offsetHour += 24; }
                //console.error(offsetHour);
                hourlybasalprofile[offsetHour].rate += basalNeeded / 3;
                hourlybasalprofile[offsetHour].rate=Math.round(hourlybasalprofile[offsetHour].rate*1000)/1000
            }
        // otherwise, figure out the percentage reduction required to the 1-3 hour prior basals
        // and adjust all of them downward proportionally
        } else if (basalNeeded < 0) {
            var threeHourBasal = 0;
            for (var offset=-3; offset < 0; offset++) {
                offsetHour = hour + offset;
                if (offsetHour < 0) { offsetHour += 24; }
                threeHourBasal += hourlybasalprofile[offsetHour].rate;
            }
            var adjustmentRatio = 1.0 + basalNeeded / threeHourBasal;
            console.error(adjustmentRatio);
            for (var offset=-3; offset < 0; offset++) {
                offsetHour = hour + offset;
                if (offsetHour < 0) { offsetHour += 24; }
                hourlybasalprofile[offsetHour].rate = hourlybasalprofile[offsetHour].rate * adjustmentRatio;
                hourlybasalprofile[offsetHour].rate=Math.round(hourlybasalprofile[offsetHour].rate*1000)/1000
            }
        }
    }
    if (pumpbasalprofile && pumpbasalprofile[0]) {
        for (var hour=0; hour < 24; hour++) {
            //console.error(hourlybasalprofile[hour],hourlypumpprofile[hour].rate*1.2);
            // 20% caps
            var maxrate = hourlypumpprofile[hour].rate * 1.2;
            var minrate = hourlypumpprofile[hour].rate / 1.2;
            if (hourlybasalprofile[hour].rate > maxrate ) {
                console.error("Limiting hour",hour,"basal to",maxrate.toFixed(2),"(which is 20% above pump basal of",hourlypumpprofile[hour].rate,")");
                hourlybasalprofile[hour].rate = maxrate;
            } else if (hourlybasalprofile[hour].rate < minrate ) {
                console.error("Limiting hour",hour,"basal to",minrate.toFixed(2),"(which is 20% below pump basal of",hourlypumpprofile[hour].rate,")");
                hourlybasalprofile[hour].rate = minrate;
            }
            hourlybasalprofile[hour].rate = Math.round(hourlybasalprofile[hour].rate*1000)/1000;
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
    var newISF = ( 0.9 * isf ) + ( 0.1 * fullNewISF );
    if (typeof(pumpISF) !== 'undefined') {
        var maxISF = pumpISF * 1.2;
        var minISF = pumpISF / 1.2;
        if (newISF > maxISF) {
            console.error("Limiting ISF to",maxISF.toFixed(2),"(which is 20% above pump ISF of",pumpISF,")");
            newISF = maxISF;
        } else if (newISF < minISF) {
            console.error("Limiting ISF to",minISF.toFixed(2),"(which is 20% below pump ISF of",pumpISF,")");
            newISF = minISF;
        }
    }
    newISF = Math.round( newISF * 1000 ) / 1000;
    //console.error(avgRatio);
    //console.error(newISF);
    console.error("p50deviation:",p50deviation,"p50bgi",p50bgi,"p50ratios:",p50ratios,"Old ISF:",isf,"fullNewISF:",fullNewISF,"newISF:",newISF);

    isf = newISF;

    // calculate net deviations while carbs are absorbing
    // measured from carb entry until COB and deviations both drop to zero

    var deviations = 0;
    var mealCarbs = 0;
    var totalMealCarbs = 0;
    var totalDeviations = 0;
    var fullNewCSF;
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
            totalMealCarbs += mealCarbs;
            totalDeviations += deviations;

        } else {
            deviations += Math.max(0*previous_autotune.min_5m_carbimpact,parseFloat(csf_glucose[i].deviation));
            mealCarbs = Math.max(mealCarbs, parseInt(csf_glucose[i].mealCarbs));
        }
    }
    // at midnight, write down the mealcarbs as total meal carbs (to prevent special case of when only one meal and it not finishing absorbing by midnight)
    // TODO: figure out what to do with dinner carbs that don't finish absorbing by midnight
    if (totalMealCarbs == 0) { totalMealCarbs += mealCarbs; }
    if (totalDeviations == 0) { totalDeviations += deviations; }
    //console.error(totalDeviations, totalMealCarbs);
    if (totalMealCarbs == 0) {
        // if no meals today, CSF is unchanged
        fullNewCSF = csf;
    } else {
        // how much change would be required to account for all of the deviations
        fullNewCSF = Math.round( (totalDeviations / totalMealCarbs)*100 )/100;
    }
    // only adjust by 10%
    newCSF = ( 0.9 * csf ) + ( 0.1 * fullNewCSF );
    // safety cap CSF
    if (typeof(pumpCSF) !== 'undefined') {
        var maxCSF = pumpCSF * 1.2;
        var minCSF = pumpCSF / 1.2;
        if (newCSF > maxCSF) {
            console.error("Limiting CSF to",maxCSF.toFixed(2),"(which is 20% above pump CSF of",pumpCSF,")");
            newCSF = maxCSF;
        } else if (newCSF < minCSF) {
            console.error("Limiting CSF to",minCSF.toFixed(2),"(which is 20% below pump CSF of",pumpCSF,")");
            newCSF = minCSF;
        } else { console.error("newCSF",newCSF,"is within 20% of",pumpCSF); }
    }
    newCSF = Math.round( newCSF * 1000 ) / 1000;
    console.error("totalMealCarbs:",totalMealCarbs,"totalDeviations:",totalDeviations,"fullNewCSF:",fullNewCSF,"newCSF:",newCSF);
    // this is where csf is set based on the outputs
    csf = newCSF;

    // reconstruct updated version of previous_autotune as autotune_output
    autotune_output = previous_autotune;
    autotune_output.basalprofile = basalprofile;
    isf_profile.sensitivities[0].sensitivity = isf;
    autotune_output.isfProfile = isf_profile;
    autotune_output.sens = isf;
    autotune_output.csf = csf;
    carb_ratio = isf / csf;
    carb_ratio = Math.round( carb_ratio * 1000 ) / 1000;
    autotune_output.carb_ratio = carb_ratio;

    return autotune_output;
}

exports = module.exports = tuneAllTheThings;

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
