
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
    console.error(isf);
    var carb_ratio = previous_autotune.carb_ratio;
    console.error(carb_ratio);
    var csf = isf / carb_ratio;
    console.error(csf);
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
    console.error(hourlybasalprofile);

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
        console.error("Hour",hour,"basal adjustment needed:",basalNeeded,"U/hr");
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

    // calculate average (?) deviation attributable to ISF
    var deviations = 0;
    var bgis = 0;
    var ratios = 0;
    var count = 0;
    for (var i=0; i < isf_glucose.length; ++i) {
       deviation = parseFloat(isf_glucose[i].deviation);
       deviations += deviation;
       bgi = parseFloat(isf_glucose[i].bgi);
       bgis += bgi;
       ratio = deviation / bgi;
       console.error("Deviation:",deviation,"BGI:",bgi,"ratio:",ratio);
       ratios += ratio;
       count++;
    }
    avgDeviation = deviations / count;
    // calculate what adjustments to ISF would have been necessary to bring deviations to zero
    avgRatio = deviations / bgis;
    // and apply 10% of that adjustment
    newIsf = ( 0.9 * isf ) + ( 0.1 * (- isf / avgRatio) );
    console.error(avgDeviation);
    console.error(avgRatio);
    console.error(newIsf);


    /*
    var treatments = find_meals(inputs);

    var opts = {
        treatments: treatments
    , profile: inputs.profile
    , pumphistory: inputs.history
    , glucose: inputs.glucose
    , prepped_glucose: inputs.prepped_glucose
    , basalprofile: inputs.basalprofile
    };

    var clock = new Date(tz(inputs.clock));

    var autotune_prep_output = sum(opts, clock);
    return autotune_prep_output;
    */
    autotune_output = previous_autotune;
    autotune_output.basalprofile = basalprofile;
    isf_profile.sensitivities[0].sensitivity = isf;
    autotune_output.isf_profile = isf_profile;
    autotune_output.csf = csf;
    carb_ratio = isf / csf;
    autotune_output.carb_ratio = carb_ratio;

    return autotune_output;
}

exports = module.exports = generate;
