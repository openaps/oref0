var tz = require('timezone');
var calcMealCOB = require('oref0/lib/determine-basal/cob-autosens');
var basal = require('oref0/lib/profile/basal');
var get_iob = require('oref0/lib/iob');
var isf = require('../profile/isf');

function diaCarbs(opts) {
    var treatments = opts.treatments;
    treatments.sort(function (a, b) {
        //console.error(a);
        var aDate = new Date(tz(a.timestamp));
        var bDate = new Date(tz(b.timestamp));
        return bDate.getTime() - aDate.getTime();
    });
    var profile_data = opts.profile;
    if (typeof(opts.glucose) !== 'undefined') {
        //var glucose_data = opts.glucose;
        var glucose_data = opts.glucose.map(function prepGlucose (obj) {
            //Support the NS sgv field to avoid having to convert in a custom way
            obj.glucose = obj.glucose || obj.sgv;
            return obj;
        });
    }
    if (typeof(opts.prepped_glucose) !== 'undefined') {
        var prepped_glucose_data = opts.prepped_glucose;
    }
    var boluses = 0;
    var carbDelay = 20 * 60 * 1000;
    var maxCarbs = 0;
    //console.error(treatments);
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
    // go through the treatments and remove any that are older than the oldest glucose value
    //console.error(treatments);
    for (var i=treatments.length-1; i>0; --i) {
        var treatment = treatments[i];
        var treatmentDate = new Date(tz(treatment.timestamp));
        var treatmentTime = treatmentDate.getTime();
        var glucose_datum = bucketed_data[bucketed_data.length-1];
        //console.error(glucose_datum);
        var bgDate = new Date(glucose_datum.date);
        var bgTime = bgDate.getTime();
        if ( treatmentTime < bgTime ) {
            treatments.splice(i,1);
        }
    }
    //console.error(treatments);
    absorbing = 0;
    mealCOB = 0;
    mealCarbs = 0;
    var type="";
    for (var i=bucketed_data.length-5; i > 0; --i) {
        var glucose_datum = bucketed_data[i];
        //console.error(glucose_datum);
        var bgDate = new Date(glucose_datum.date);
        var bgTime = bgDate.getTime();
        // As we're processing each data point, go through the treatment.carbs and see if any of them are older than
        // the current BG data point.  If so, add those carbs to COB.
        var treatment = treatments[treatments.length-1];
        var treatmentDate = new Date(tz(treatment.timestamp));
        var treatmentTime = treatmentDate.getTime();
        //console.error(treatmentDate);
        if ( treatmentTime < bgTime ) {
            if (treatment.carbs >= 1) {
                mealCOB += parseFloat(treatment.carbs);
                mealCarbs += parseFloat(treatment.carbs);
            }
            treatments.pop();
        }

        var bg;
        var avgDelta;
        var delta;
        // TODO: re-implement interpolation to avoid issues here with gaps
        // calculate avgDelta as last 4 datapoints to better catch more rises after COB hits zero
        if (typeof(bucketed_data[i].glucose) != 'undefined') {
            //console.error(bucketed_data[i]);
            bg = bucketed_data[i].glucose;
            if ( bg < 40 || bucketed_data[i+4].glucose < 40) {
                process.stderr.write("!");
                continue;
            }
            avgDelta = (bg - bucketed_data[i+4].glucose)/4;
            delta = (bg - bucketed_data[i+1].glucose);
        } else { console.error("Could not find glucose data"); }

        avgDelta = avgDelta.toFixed(2);
        glucose_datum.avgDelta = avgDelta;

        var sens = isf.isfLookup(iob_inputs.profile.isfProfile,bgDate);
        iob_inputs.clock=bgDate.toISOString();
        // use the average of the last 4 hours' basals to help convergence
        currentBasal = basal.basalLookup(opts.basalprofile, bgDate);
        bgDate1hAgo = new Date(bgTime-1*60*60*1000);
        bgDate2hAgo = new Date(bgTime-2*60*60*1000);
        bgDate3hAgo = new Date(bgTime-3*60*60*1000);
        basal1hAgo = basal.basalLookup(opts.basalprofile, bgDate1hAgo);
        basal2hAgo = basal.basalLookup(opts.basalprofile, bgDate2hAgo);
        basal3hAgo = basal.basalLookup(opts.basalprofile, bgDate3hAgo);
        var sum = [currentBasal,basal1hAgo,basal2hAgo,basal3hAgo].reduce(function(a, b) { return a + b; });
        iob_inputs.profile.current_basal = Math.round((sum/4)*1000)/1000;

        //console.error(currentBasal,basal1hAgo,basal2hAgo,basal3hAgo,iob_inputs.profile.current_basal);
        basalBgi = Math.round(( currentBasal * sens / 60 * 5 )*100)/100; // U/hr * mg/dL/U * 1 hr / 60 minutes * 5 = mg/dL/5m 
        //console.log(JSON.stringify(iob_inputs.profile));
        var iob = get_iob(iob_inputs)[0];
        //console.error(JSON.stringify(iob));

        var bgi = Math.round(( -iob.activity * sens * 5 )*100)/100;
        glucose_datum.bgi = bgi;
        deviation = avgDelta-bgi;
        deviation = deviation.toFixed(2);
        glucose_datum.deviation = deviation;



        // Then, calculate carb absorption for that 5m interval using the deviation.
        if ( mealCOB > 0 ) {
            var profile = profile_data;
            ci = Math.max(deviation, profile.min_5m_carbimpact);
            absorbed = ci * profile.carb_ratio / sens;
            mealCOB = Math.max(0, mealCOB-absorbed);
        }
        // Store the COB, and use it as the starting point for the next data point.

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
                console.error(glucose_datum.mealAbsorption);
            }
            type="csf";
            glucose_datum.mealCarbs = mealCarbs;
            //if (i == 0) { glucose_datum.mealAbsorption = "end"; }
            csf_glucose_data.push(glucose_datum);
        } else {
            // check previous "type" value, and if it was csf, set a mealAbsorption end flag
            if ( type === "csf" ) {
                csf_glucose_data[csf_glucose_data.length-1].mealAbsorption = "end";
                console.error(csf_glucose_data[csf_glucose_data.length-1].mealAbsorption);
            }

            // Go through the remaining time periods and divide them into periods where scheduled basal insulin activity dominates. This would be determined by calculating the BG impact of scheduled basal insulin (for example 1U/hr * 48 mg/dL/U ISF = 48 mg/dL/hr = 5 mg/dL/5m), and comparing that to BGI from bolus and net basal insulin activity.
            // When BGI is positive (insulin activity is negative), we want to use that data to tune basals
            // When BGI is smaller than about 1/4 of basalBGI, we want to use that data to tune basals
            // When BGI is negative and more than about 1/4 of basalBGI, we can use that data to tune ISF,
            // unless avgDelta is positive: then that's some sort of unexplained rise we don't want to use for ISF or basals
            if (basalBgi > -4 * bgi) {
                type="basal";
                basal_glucose_data.push(glucose_datum);
            } else {
                if (avgDelta > 0 ) {
                    //type="unknown"
                    type="basal"
                } else {
                    type="isf";
                    isf_glucose_data.push(glucose_datum);
                }
            }
        }
        console.error(absorbing.toString(),"mealCOB:",mealCOB.toFixed(1),"mealCarbs:",mealCarbs,"basalBgi:",basalBgi.toFixed(1),"bgi:",bgi.toFixed(1),"at",bgDate,"dev:",deviation,"avgDelta:",avgDelta,type);
    }

    return {
        csf_glucose_data: csf_glucose_data,
        isf_glucose_data: isf_glucose_data,
        basal_glucose_data: basal_glucose_data
    };
}

exports = module.exports = diaCarbs;

