var tz = require('timezone');
var calcMealCOB = require('oref0/lib/determine-basal/cob-autosens');
var basal = require('oref0/lib/profile/basal');
var get_iob = require('oref0/lib/iob');
var isf = require('../profile/isf');

function diaCarbs(opts, time) {
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    if (typeof(opts.glucose) !== 'undefined') {
        var glucose_data = opts.glucose;
    }
    if (typeof(opts.prepped_glucose) !== 'undefined') {
        var prepped_glucose_data = opts.prepped_glucose;
    }
    var boluses = 0;
    var carbDelay = 20 * 60 * 1000;
    var maxCarbs = 0;
    var mealCarbTime = time.getTime();
    if (!treatments) return {};

    //console.error(glucose_data);
    var iob_inputs = {
        profile: profile_data
    ,   history: opts.pumphistory
    };
    var COB_inputs = {
        glucose_data: glucose_data
    ,   iob_inputs: iob_inputs
    ,   basalprofile: opts.basalprofile
    ,   mealTime: mealCarbTime
    };
    var mealCOB = 0;
    var csf_glucose_data = [];
    var isf_glucose_data = [];
    var basal_glucose_data = [];

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
        var elapsed_minutes = (bgTime - lastbgTime)/(60*1000);
        if(Math.abs(elapsed_minutes) > 2) {
            j++;
            bucketed_data[j]=glucose_data[i];
            bucketed_data[j].date = bgTime.getTime();
        } else {
            bucketed_data[j].glucose = (bucketed_data[j].glucose + glucose_data[i].glucose)/2;
        }
    }
    //console.error(bucketed_data);
    //console.error(bucketed_data[bucketed_data.length-1]);
    absorbing = 0;
    var type="";
    for (var i=bucketed_data.length-4; i > 0; --i) {
        var glucose_datum = bucketed_data[i];
        //console.error(glucose_datum);
        var bgDate = new Date(glucose_datum.date);
        var bgTime = bgDate.getTime();
        // TODO: if there is already a record with bgTime in the prepped_glucose_data, use that
        COB_inputs.bgTime = bgDate;
        mealCOB = 0;
        mealCarbs = 0;
        var carbs = 0;
        treatments.forEach(function(treatment) {
            var dia_ago = bgTime - 1.5*profile_data.dia*60*60*1000;
            var treatmentDate = new Date(tz(treatment.timestamp));
            var treatmentTime = treatmentDate.getTime();
            if (treatmentTime > dia_ago && treatmentTime <= bgTime) {
                if (treatment.carbs >= 1) {
                    //console.error(treatment.carbs, maxCarbs, treatmentDate);
                    carbs += parseFloat(treatment.carbs);
                    mealCarbs += parseFloat(treatment.carbs);
                    COB_inputs.mealTime = treatmentTime;
                    var myCarbsAbsorbed = calcMealCOB(COB_inputs).carbsAbsorbed;
                    //console.error("myCarbsAbsorbed: ",myCarbsAbsorbed);
                    var myMealCOB = Math.max(0, carbs - myCarbsAbsorbed);
                    if (myMealCOB == 0) { mealCarbs = 0; }
                    //console.error("myMealCOB: ",myMealCOB);
                    mealCOB = Math.max(mealCOB, myMealCOB);
                }
                if (treatment.bolus >= 0.1) {
                    boluses += parseFloat(treatment.bolus);
                }
            }
        });
        glucose_datum.mealCarbs = mealCarbs;

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
        glucose_datum.avgDelta = avgDelta;

        var sens = isf.isfLookup(iob_inputs.profile.isfProfile,bgDate);
        iob_inputs.clock=bgDate.toISOString();
        currentBasal = basal.basalLookup(opts.basalprofile, bgDate);
        iob_inputs.profile.current_basal = currentBasal;
        basalBgi = Math.round(( currentBasal * sens / 60 * 5 )*100)/100; // U/hr * mg/dL/U * 1 hr / 60 minutes * 5 = mg/dL/5m 
        //console.log(JSON.stringify(iob_inputs.profile));
        var iob = get_iob(iob_inputs)[0];
        //console.error(JSON.stringify(iob));

        var bgi = Math.round(( -iob.activity * sens * 5 )*100)/100;
        glucose_datum.bgi = bgi;
        deviation = avgDelta-bgi;
        deviation = deviation.toFixed(2);
        glucose_datum.deviation = deviation;
        // If mealCOB is zero but all deviations since hitting COB=0 are positive, assign those data points to csf_glucose_data
        // Once deviations go negative for at least one data point after COB=0, we can use the rest of the data to tune ISF or basals
        if (mealCOB > 0 || absorbing || mealCarbs > 0) {
            if (deviation > 0) {
                absorbing = 1;
            } else {
                absorbing = 0;
            }
            if ( ! absorbing && ! mealCOB ) {
                mealCarbs = 0;
            }
            // check previous "type" value, and if it wasn't csf, set a mealAbsorption start flag
            //console.error(type);
            if ( type != "csf" ) {
                glucose_datum.mealAbsorption = "start";
                console.error(glucose_datum);
            }
            type="csf";
            csf_glucose_data.push(glucose_datum);
        } else {
            // check previous "type" value, and if it was csf, set a mealAbsorption end flag
            if ( type === "csf" ) {
                csf_glucose_data[csf_glucose_data.length-1].mealAbsorption = "end";
                console.error(csf_glucose_data[csf_glucose_data.length-1]);
            }

            // Go through the remaining time periods and divide them into periods where scheduled basal insulin activity dominates. This would be determined by calculating the BG impact of scheduled basal insulin (for example 1U/hr * 48 mg/dL/U ISF = 48 mg/dL/hr = 5 mg/dL/5m), and comparing that to BGI from bolus and net basal insulin activity.
            // When BGI is positive (insulin activity is negative) (or BG is rising?), we want to use that data to tune basals
            // When BGI is smaller than about 1/4 of basalBGI, we want to use that data to tune basals
            // When BGI is negative and more than about 1/4 of basalBGI, we can use that data to tune ISF
            // TODO: figure out if rising BGs work better in basal or ISF
            //if (basalBgi > -4 * bgi || avgDelta > 0) {
            if (basalBgi > -4 * bgi) {
                type="basal";
                basal_glucose_data.push(glucose_datum);
            } else {
                type="isf";
                isf_glucose_data.push(glucose_datum);
            }
        }
        console.error(absorbing.toString(),"MealCOB:",mealCOB.toFixed(1),"MealCarbs:",mealCarbs,"basal BGI:",basalBgi.toFixed(1),"BGI:",bgi.toFixed(1),"at",bgDate, "Dev:",deviation,"avgDelta:",avgDelta,type);
    }

    return {
        csf_glucose_data: csf_glucose_data,
        isf_glucose_data: isf_glucose_data,
        basal_glucose_data: basal_glucose_data
    };
}

exports = module.exports = diaCarbs;

