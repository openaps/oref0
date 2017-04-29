// does three things - tunes basals, ISF, and CSF

function tuneAllTheThings (inputs) {

    var previousAutotune = inputs.previousAutotune;
    //console.error(previousAutotune);
    var pumpProfile = inputs.pumpProfile;
    var pumpBasalProfile = pumpProfile.basalprofile;
    //console.error(pumpBasalProfile);
    var basalProfile = previousAutotune.basalprofile;
    //console.error(basalProfile);
    var isfProfile = previousAutotune.isfProfile;
    //console.error(isfProfile);
    var ISF = isfProfile.sensitivities[0].sensitivity;
    //console.error(ISF);
    var carbRatio = previousAutotune.carb_ratio;
    //console.error(carbRatio);
    var CSF = ISF / carbRatio;
    // conditional on there being a pump profile; if not then skip
    if (pumpProfile) { pumpISFProfile = pumpProfile.isfProfile; }
    if (pumpISFProfile && pumpISFProfile.sensitivities[0]) {
        pumpISF = pumpISFProfile.sensitivities[0].sensitivity;
        pumpCarbRatio = pumpProfile.carb_ratio;
        pumpCSF = pumpISF / pumpCarbRatio;
    }
    //console.error(CSF);
    var preppedGlucose = inputs.preppedGlucose;
    var CSFGlucose = preppedGlucose.CSFGlucoseData;
    //console.error(CSFGlucose[0]);
    var ISFGlucose = preppedGlucose.ISFGlucoseData;
    //console.error(ISFGlucose[0]);
    var basalGlucose = preppedGlucose.basalGlucoseData;
    //console.error(basalGlucose[0]);

    // convert the basal profile to hourly if it isn't already
    hourlyBasalProfile = [];
    hourlyPumpProfile = [];
    for (var i=0; i < 24; i++) {
        // aututuned basal profile
        for (var j=0; j < basalProfile.length; ++j) {
            if (basalProfile[j].minutes <= i * 60) {
                if (basalProfile[j].rate == 0) {
                    console.error("ERROR: bad basalProfile",basalProfile[j]);
                    return;
                }
                hourlyBasalProfile[i] = JSON.parse(JSON.stringify(basalProfile[j]));
            }
        }
        hourlyBasalProfile[i].i=i;
        hourlyBasalProfile[i].minutes=i*60;
        var zeroPadHour = ("000"+i).slice(-2);
        hourlyBasalProfile[i].start=zeroPadHour + ":00:00";
        hourlyBasalProfile[i].rate=Math.round(hourlyBasalProfile[i].rate*1000)/1000
        // pump basal profile
        if (pumpBasalProfile && pumpBasalProfile[0]) {
            for (var j=0; j < pumpBasalProfile.length; ++j) {
                //console.error(pumpBasalProfile[j]);
                if (pumpBasalProfile[j].rate == 0) {
                    console.error("ERROR: bad pumpBasalProfile",pumpBasalProfile[j]);
                    return;
                }
                if (pumpBasalProfile[j].minutes <= i * 60) {
                    hourlyPumpProfile[i] = JSON.parse(JSON.stringify(pumpBasalProfile[j]));
                }
            }
            hourlyPumpProfile[i].i=i;
            hourlyPumpProfile[i].minutes=i*60;
            hourlyPumpProfile[i].rate=Math.round(hourlyPumpProfile[i].rate*1000)/1000
        }
    }
    //console.error(hourlyPumpProfile);
    //console.error(hourlyBasalProfile);

    // look at net deviations for each hour
    for (var hour=0; hour < 24; hour++) {
        var deviations = 0;
        for (var i=0; i < basalGlucose.length; ++i) {
            //console.error(basalGlucose[i].dateString);
            splitString = basalGlucose[i].dateString.split("T");
            timeString = splitString[1];
            splitTime = timeString.split(":");
            myHour = parseInt(splitTime[0]);
            if (hour == myHour) {
                //console.error(basalGlucose[i].deviation);
                deviations += parseFloat(basalGlucose[i].deviation);
            }
        }
        deviations = Math.round( deviations * 1000 ) / 1000
        //console.error("Hour",hour.toString(),"total deviations:",deviations,"mg/dL");
        // calculate how much less or additional basal insulin would have been required to eliminate the deviations
        // only apply 20% of the needed adjustment to keep things relatively stable
        basalNeeded = 0.2 * deviations / ISF;
        basalNeeded = Math.round( basalNeeded * 1000 ) / 1000
        // if basalNeeded is positive, adjust each of the 1-3 hour prior basals by 10% of the needed adjustment
        console.error("Hour",hour,"basal adjustment needed:",basalNeeded,"U/hr");
        if (basalNeeded > 0 ) {
            for (var offset=-3; offset < 0; offset++) {
                offsetHour = hour + offset;
                if (offsetHour < 0) { offsetHour += 24; }
                //console.error(offsetHour);
                hourlyBasalProfile[offsetHour].rate += basalNeeded / 3;
                hourlyBasalProfile[offsetHour].rate=Math.round(hourlyBasalProfile[offsetHour].rate*1000)/1000
            }
        // otherwise, figure out the percentage reduction required to the 1-3 hour prior basals
        // and adjust all of them downward proportionally
        } else if (basalNeeded < 0) {
            var threeHourBasal = 0;
            for (var offset=-3; offset < 0; offset++) {
                offsetHour = hour + offset;
                if (offsetHour < 0) { offsetHour += 24; }
                threeHourBasal += hourlyBasalProfile[offsetHour].rate;
            }
            var adjustmentRatio = 1.0 + basalNeeded / threeHourBasal;
            //console.error(adjustmentRatio);
            for (var offset=-3; offset < 0; offset++) {
                offsetHour = hour + offset;
                if (offsetHour < 0) { offsetHour += 24; }
                hourlyBasalProfile[offsetHour].rate = hourlyBasalProfile[offsetHour].rate * adjustmentRatio;
                hourlyBasalProfile[offsetHour].rate=Math.round(hourlyBasalProfile[offsetHour].rate*1000)/1000
            }
        }
    }
    if (pumpBasalProfile && pumpBasalProfile[0]) {
        for (var hour=0; hour < 24; hour++) {
            //console.error(hourlyBasalProfile[hour],hourlyPumpProfile[hour].rate*1.2);
            // cap adjustments at autosens_max and autosens_min
            autotuneMax = pumpProfile.autosens_max;
            autotuneMin = pumpProfile.autosens_min;
            var maxRate = hourlyPumpProfile[hour].rate * autotuneMax;
            var minRate = hourlyPumpProfile[hour].rate * autotuneMin;
            if (hourlyBasalProfile[hour].rate > maxRate ) {
                console.error("Limiting hour",hour,"basal to",maxRate.toFixed(2),"(which is",autotuneMax,"* pump basal of",hourlyPumpProfile[hour].rate,")");
                //console.error("Limiting hour",hour,"basal to",maxRate.toFixed(2),"(which is 20% above pump basal of",hourlyPumpProfile[hour].rate,")");
                hourlyBasalProfile[hour].rate = maxRate;
            } else if (hourlyBasalProfile[hour].rate < minRate ) {
                console.error("Limiting hour",hour,"basal to",minRate.toFixed(2),"(which is",autotuneMin,"* pump basal of",hourlyPumpProfile[hour].rate,")");
                //console.error("Limiting hour",hour,"basal to",minRate.toFixed(2),"(which is 20% below pump basal of",hourlyPumpProfile[hour].rate,")");
                hourlyBasalProfile[hour].rate = minRate;
            }
            hourlyBasalProfile[hour].rate = Math.round(hourlyBasalProfile[hour].rate*1000)/1000;
        }
    }

    console.error(hourlyBasalProfile);
    basalProfile = hourlyBasalProfile;

    // calculate median deviation and bgi in data attributable to ISF
    var deviations = [];
    var BGIs = [];
    var avgDeltas = [];
    var ratios = [];
    var count = 0;
    for (var i=0; i < ISFGlucose.length; ++i) {
        deviation = parseFloat(ISFGlucose[i].deviation);
        deviations.push(deviation);
        BGI = parseFloat(ISFGlucose[i].BGI);
        BGIs.push(BGI);
        avgDelta = parseFloat(ISFGlucose[i].avgDelta);
        avgDeltas.push(avgDelta);
        ratio = 1 + deviation / BGI;
        //console.error("Deviation:",deviation,"BGI:",BGI,"avgDelta:",avgDelta,"ratio:",ratio);
        ratios.push(ratio);
        count++;
    }
    avgDeltas.sort(function(a, b){return a-b});
    BGIs.sort(function(a, b){return a-b});
    deviations.sort(function(a, b){return a-b});
    ratios.sort(function(a, b){return a-b});
    p50deviation = percentile(deviations, 0.50);
    p50BGI = percentile(BGIs, 0.50);
    p50ratios = Math.round( percentile(ratios, 0.50) * 1000)/1000;
    if (count < 5) {
        // leave ISF unchanged if fewer than 5 ISF data points
        fullNewISF = ISF;
    } else {
        // calculate what adjustments to ISF would have been necessary to bring median deviation to zero
        fullNewISF = ISF * p50ratios;
    }
    fullNewISF = Math.round( fullNewISF * 1000 ) / 1000;
    // adjust the target ISF to be a weighted average of fullNewISF and pumpISF
    var adjustmentFraction;
    if (pumpProfile.autotune_isf_adjustmentFraction) {
        adjustmentFraction = pumpProfile.autotune_isf_adjustmentFraction;
    } else {
        adjustmentFraction = 0.5;
    }
    if (typeof(pumpISF) !== 'undefined') {
        var adjustedISF = adjustmentFraction*fullNewISF + (1-adjustmentFraction)*pumpISF;
        // cap adjustedISF before applying 10%
        if (adjustedISF > maxISF) {
            console.error("Limiting adjusted ISF of",adjustedISF.toFixed(2),"to",maxISF.toFixed(2),"(which is pump ISF of",pumpISF,"/",autotuneMin,")");
            adjustedISF = maxISF;
        } else if (adjustedISF < minISF) {
            console.error("Limiting adjusted ISF of",adjustedISF.toFixed(2),"to",minISF.toFixed(2),"(which is pump ISF of",pumpISF,"/",autotuneMax,")");
            adjustedISF = minISF;
        }

        // and apply 10% of that adjustment
        var newISF = ( 0.9 * ISF ) + ( 0.1 * adjustedISF );

        // low autosens ratio = high ISF
        var maxISF = pumpISF / autotuneMin;
        // high autosens ratio = low ISF
        var minISF = pumpISF / autotuneMax;
        if (newISF > maxISF) {
            console.error("Limiting ISF of",newISF.toFixed(2),"to",maxISF.toFixed(2),"(which is pump ISF of",pumpISF,"/",autotuneMin,")");
            newISF = maxISF;
        } else if (newISF < minISF) {
            console.error("Limiting ISF of",newISF.toFixed(2),"to",minISF.toFixed(2),"(which is pump ISF of",pumpISF,"/",autotuneMax,")");
            newISF = minISF;
        }
    }
    newISF = Math.round( newISF * 1000 ) / 1000;
    //console.error(avgRatio);
    //console.error(newISF);
    console.error("p50deviation:",p50deviation,"p50BGI",p50BGI,"p50ratios:",p50ratios,"Old ISF:",ISF,"fullNewISF:",fullNewISF,"adjustedISF:",adjustedISF,"newISF:",newISF);

    ISF = newISF;

    // calculate net deviations while carbs are absorbing
    // measured from carb entry until COB and deviations both drop to zero

    var deviations = 0;
    var mealCarbs = 0;
    var totalMealCarbs = 0;
    var totalDeviations = 0;
    var fullNewCSF;
    //console.error(CSFGlucose[0].mealAbsorption);
    //console.error(CSFGlucose[0]);
    for (var i=0; i < CSFGlucose.length; ++i) {
        //console.error(CSFGlucose[i].mealAbsorption, i);
        if ( CSFGlucose[i].mealAbsorption === "start" ) {
            deviations = 0;
            mealCarbs = parseInt(CSFGlucose[i].mealCarbs);
        } else if (CSFGlucose[i].mealAbsorption === "end") {
            deviations += parseFloat(CSFGlucose[i].deviation);
            // compare the sum of deviations from start to end vs. current CSF * mealCarbs
            //console.error(CSF,mealCarbs);
            csfRise = CSF * mealCarbs;
            //console.error(deviations,ISF);
            //console.error("csfRise:",csfRise,"deviations:",deviations);
            totalMealCarbs += mealCarbs;
            totalDeviations += deviations;

        } else {
            deviations += Math.max(0*previousAutotune.min_5m_carbimpact,parseFloat(CSFGlucose[i].deviation));
            mealCarbs = Math.max(mealCarbs, parseInt(CSFGlucose[i].mealCarbs));
        }
    }
    // at midnight, write down the mealcarbs as total meal carbs (to prevent special case of when only one meal and it not finishing absorbing by midnight)
    // TODO: figure out what to do with dinner carbs that don't finish absorbing by midnight
    if (totalMealCarbs == 0) { totalMealCarbs += mealCarbs; }
    if (totalDeviations == 0) { totalDeviations += deviations; }
    //console.error(totalDeviations, totalMealCarbs);
    if (totalMealCarbs == 0) {
        // if no meals today, CSF is unchanged
        fullNewCSF = CSF;
    } else {
        // how much change would be required to account for all of the deviations
        fullNewCSF = Math.round( (totalDeviations / totalMealCarbs)*100 )/100;
    }
    // only adjust by 10%
    newCSF = ( 0.9 * CSF ) + ( 0.1 * fullNewCSF );
    // safety cap CSF
    if (typeof(pumpCSF) !== 'undefined') {
        var maxCSF = pumpCSF * autotuneMax;
        var minCSF = pumpCSF * autotuneMin;
        if (newCSF > maxCSF) {
            console.error("Limiting CSF to",maxCSF.toFixed(2),"(which is",autotuneMax,"* pump CSF of",pumpCSF,")");
            newCSF = maxCSF;
        } else if (newCSF < minCSF) {
            console.error("Limiting CSF to",minCSF.toFixed(2),"(which is",autotuneMin,"* pump CSF of",pumpCSF,")");
            newCSF = minCSF;
        } //else { console.error("newCSF",newCSF,"is close enough to",pumpCSF); }
    }
    newCSF = Math.round( newCSF * 1000 ) / 1000;
    console.error("totalMealCarbs:",totalMealCarbs,"totalDeviations:",totalDeviations,"fullNewCSF:",fullNewCSF,"newCSF:",newCSF);
    // this is where CSF is set based on the outputs
    CSF = newCSF;

    // reconstruct updated version of previousAutotune as autotuneOutput
    autotuneOutput = previousAutotune;
    autotuneOutput.basalprofile = basalProfile;
    isfProfile.sensitivities[0].sensitivity = ISF;
    autotuneOutput.isfProfile = isfProfile;
    autotuneOutput.sens = ISF;
    autotuneOutput.csf = CSF;
    carbRatio = ISF / CSF;
    carbRatio = Math.round( carbRatio * 1000 ) / 1000;
    autotuneOutput.carb_ratio = carbRatio;

    return autotuneOutput;
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
