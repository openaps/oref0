#!/usr/bin/env node

function getLastGlucose(data) {
    
    var now = data[0];
    var last = data[1];
    var avg;
    //TODO: calculate average using system_time instead of assuming 1 data point every 5m
    if (typeof data[3] !== 'undefined' && data[3].glucose > 30) {
        avg = ( now.glucose - data[3].glucose) / 3;
    } else if (typeof data[2] !== 'undefined' && data[2].glucose > 30) {
        avg = ( now.glucose - data[2].glucose) / 2;
    } else if (typeof data[1] !== 'undefined' && data[1].glucose > 30) {
        avg = now.glucose - data[1].glucose;
    } else { avg = 0; }
    var o = {
        delta: now.glucose - last.glucose
        , glucose: now.glucose
        , avgdelta: avg
    };
    
    return o;
    
}

function setTempBasal(rate, duration) {
    
    maxSafeBasal = Math.min(profile_data.max_basal, 3 * profile_data.max_daily_basal, 4 * profile_data.current_basal);
    
    if (rate < 0) { rate = 0; } // if >30m @ 0 required, zero temp will be extended to 30m instead
    else if (rate > maxSafeBasal) { rate = maxSafeBasal; }
    
    // rather than canceling temps, always set the current basal as a 30m temp
    // so we can see on the pump that openaps is working
    if (duration == 0) {
        rate = profile_data.current_basal;
        duration  = 30;
    }

    requestedTemp.duration = duration;
    requestedTemp.rate = Math.round((Math.round(rate / 0.05) * 0.05)*100)/100;
};


if (!module.parent) {
    var iob_input = process.argv.slice(2, 3).pop()
    var temps_input = process.argv.slice(3, 4).pop()
    var glucose_input = process.argv.slice(4, 5).pop()
    var profile_input = process.argv.slice(5, 6).pop()
    var offline_input = process.argv.slice(6, 7).pop()

    if (!iob_input || !temps_input || !glucose_input || !profile_input) {
        console.error('usage: ', process.argv.slice(0, 2), '<iob.json> <current-temps.json> <glucose.json> <profile.json> [Offline]');
        process.exit(1);
    }
    
    var cwd = process.cwd()
    var glucose_data = require(cwd + '/' + glucose_input);
    var temps_data = require(cwd + '/' + temps_input);
    var iob_data = require(cwd + '/' + iob_input);
    var profile_data = require(cwd + '/' + profile_input);
    
    if (typeof profile_data === 'undefined' || typeof profile_data.current_basal === 'undefined') {
        console.error('Error: could not get current basal rate');
        process.exit(1);
    }

    var max_iob = profile_data.max_iob; // maximum amount of non-bolus IOB OpenAPS will ever deliver

    // if target_bg is set, great. otherwise, if min and max are set, then set target to their average
    var target_bg;
    if (typeof profile_data.target_bg !== 'undefined') {
        target_bg = profile_data.target_bg;
    } else {
        if (typeof profile_data.max_bg !== 'undefined' && typeof profile_data.max_bg !== 'undefined') {
            target_bg = (profile_data.min_bg + profile_data.max_bg) / 2;
        } else {
            console.error('Error: could not determine target_bg');
            process.exit(1);
        }
    }
    
    var glucose_status = getLastGlucose(glucose_data);
    var bg = glucose_status.glucose;
    var tick;
    if (glucose_status.delta >= 0) { tick = "+" + glucose_status.delta; }
    else { tick = glucose_status.delta; }
    console.error("IOB: " + iob_data.iob.toFixed(2) + ", Bolus IOB: " + iob_data.bolusiob.toFixed(2));
    var bgi = -iob_data.activity * profile_data.sens * 5;
    console.error("Avg. Delta: " + glucose_status.avgdelta.toFixed(1) + ", BGI: " + bgi.toFixed(1));
    // project deviation over next 15 minutes
    var deviation = Math.round( 15 / 5 * ( glucose_status.avgdelta - bgi ) );
    console.error("15m deviation: " + deviation.toFixed(0));
    var bolusContrib = iob_data.bolusiob * profile_data.sens;
    var naive_eventualBG = Math.round( bg - (iob_data.iob * profile_data.sens) );
    var eventualBG = naive_eventualBG + deviation;
    var naive_snoozeBG = Math.round( naive_eventualBG + bolusContrib );
    var snoozeBG = naive_snoozeBG + deviation;
    console.error("BG: " + bg + tick + " -> " + eventualBG + "-" + snoozeBG + " (Unadjusted: " + naive_eventualBG + "-" + naive_snoozeBG + ")");
    if (typeof eventualBG === 'undefined') { console.error('Error: could not calculate eventualBG'); }
    var requestedTemp = {
        'temp': 'absolute'
        , 'bg': bg
        , 'tick': tick
        , 'eventualBG': eventualBG
        , 'snoozeBG': snoozeBG
    };
    
    
    
    //if old reading from Dexcom do nothing
    
    var systemTime = new Date();
    var bgTime;
    if (glucose_data[0].display_time) {
        bgTime = new Date(glucose_data[0].display_time.replace('T', ' '));
    } else if (glucose_data[0].dateString) {
        bgTime = new Date(glucose_data[0].dateString);
    } else { console.error("Could not determine last BG time"); }
    var minAgo = (systemTime - bgTime) / 60 / 1000
    var threshold = profile_data.min_bg - 30;
    var reason="";
    
    if (minAgo < 10 && minAgo > -5) { // Dexcom data is recent, but not far in the future
        
        if (bg > 10) {  //Dexcom is in ??? mode or calibrating, do nothing. Asked @benwest for raw data in iter_glucose
            
            if (bg < threshold) { // low glucose suspend mode: BG is < ~80
                reason = "BG " + bg + "<" + threshold;
                console.error(reason);
                if (glucose_status.delta > 0) { // if BG is rising
                    if (temps_data.rate > profile_data.current_basal) { // if a high-temp is running
                        setTempBasal(0, 0); // cancel high temp
                    } else if (temps_data.duration && eventualBG > profile_data.max_bg) { // if low-temped and predicted to go high from negative IOB
                        setTempBasal(0, 0); // cancel low temp
                    } else {
                        reason = bg + "<" + threshold + "; no high-temp to cancel";
                        console.error(reason);
                    }
                }
                else { // BG is not yet rising
                    setTempBasal(0, 30);
                }
            
            } else {
                
                // if BG is rising but eventual BG is below min, or BG is falling but eventual BG is above min
                if ((glucose_status.delta > 0 && eventualBG < profile_data.min_bg) || (glucose_status.delta < 0 && eventualBG >= profile_data.min_bg)) {
                    if (temps_data.duration > 0) { // if there is currently any temp basal running
                        // if it's a low-temp and eventualBG < profile_data.max_bg, let it run a bit longer
                        if (temps_data.rate <= profile_data.current_basal && eventualBG < profile_data.max_bg) {
                            reason = "BG" + tick + " but " + eventualBG + "<" + profile_data.max_bg;
                            console.error(reason);
                        } else {
                            reason = glucose_status.delta + " and " + eventualBG;
                            setTempBasal(0, 0); // cancel temp
                        }
                    } else {
                        reason = tick + "; no temp to cancel";
                        console.error(reason);
                    }
        
                } else if (eventualBG < profile_data.min_bg) { // if eventual BG is below target:
                    // if this is just due to boluses, we can snooze until the bolus IOB decays (at double speed)
                    if (snoozeBG > profile_data.min_bg) { // if adding back in the bolus contribution BG would be above min
                        // if BG is falling and high-temped, or rising and low-temped, cancel
                        if (glucose_status.delta < 0 && temps_data.rate > profile_data.current_basal) {
                            reason = tick + " and " + temps_data.rate + ">" + profile_data.current_basal;
                            setTempBasal(0, 0); // cancel temp
                        } else if (glucose_status.delta > 0 && temps_data.rate < profile_data.current_basal) {
                            reason = tick + " and " + temps_data.rate + "<" + profile_data.current_basal;
                            setTempBasal(0, 0); // cancel temp
                        } else {
                            reason = "bolus snooze: eventual BG range " + eventualBG + "-" + snoozeBG;
                            console.error(reason);
                        }
                    } else {
                        // calculate 30m low-temp required to get projected BG up to target
                        // negative insulin required to get up to min:
                        //var insulinReq = Math.max(0, (target_bg - eventualBG) / profile_data.sens);
                        // use snoozeBG instead of eventualBG to more gradually ramp in any counteraction of the user's boluses
                        var insulinReq = Math.min(0, (snoozeBG - target_bg) / profile_data.sens);
                        // rate required to deliver insulinReq less insulin over 30m:
                        var rate = profile_data.current_basal + (2 * insulinReq);
                        rate = Math.round( rate * 1000 ) / 1000;
                        // if required temp < existing temp basal
                        if (typeof temps_data.rate !== 'undefined' && (temps_data.duration > 0 && rate > temps_data.rate - 0.1)) {
                            reason = temps_data.rate + "<~" + rate;
                            console.error(reason);
                        } else {
                            reason = "Eventual BG " + eventualBG + "<" + profile_data.min_bg;
                            //console.error(reason);
                            setTempBasal(rate, 30);
                        }
                    }

                } else if (eventualBG > profile_data.max_bg) { // if eventual BG is above target:
                    // if iob is over max, just cancel any temps
                    var basal_iob = iob_data.iob - iob_data.bolusiob;
                    if (basal_iob > max_iob) {
                        reason = basal_iob + ">" + max_iob;
                        setTempBasal(0, 0);
                    }
                    // calculate 30m high-temp required to get projected BG down to target
                    // additional insulin required to get down to max bg:
                    var insulinReq = (eventualBG - target_bg) / profile_data.sens;
                    //TODO: verify this is working
                    // if that would put us over max_iob, then reduce accordingly
                    insulinReq = Math.min(insulinReq, max_iob-basal_iob);

                    // rate required to deliver insulinReq more insulin over 30m:
                    var rate = profile_data.current_basal + (2 * insulinReq);
                    rate = Math.round( rate * 1000 ) / 1000;
                    maxSafeBasal = Math.min(profile_data.max_basal, 3 * profile_data.max_daily_basal, 4 * profile_data.current_basal);
                    if (rate > maxSafeBasal) {
                        rate = maxSafeBasal;
                        //console.error(maxSafeBasal);
                    }
                    var insulinScheduled = temps_data.duration * (temps_data.rate - profile_data.current_basal) / 60;
                    if (insulinScheduled > insulinReq + 0.1) { // if current temp would deliver more than the required insulin (plus a 0.1U fudge factor), lower the rate
                        reason = temps_data.duration + "@" + temps_data.rate + " > " + insulinReq + "U";
                        setTempBasal(rate, 30);
                    }
                    else if (typeof temps_data.rate !== 'undefined' && (temps_data.duration > 0 && rate < temps_data.rate + 0.1)) { // if required temp < existing temp basal
                        reason = temps_data.rate + ">~" + rate;
                        console.error(reason);
                    } else { // required temp > existing temp basal
                        reason = temps_data.rate + "<" + rate;
                        setTempBasal(rate, 30);
                    }
        
                } else { 
                    reason = eventualBG + " is in range. No temp required.";
                    if (temps_data.duration > 0) { // if there is currently any temp basal running
                        setTempBasal(0, 0); // cancel temp
                    } else {
                        console.error(reason);
                    }
                }
            }
            
            if (offline_input == 'Offline') {
                // if no temp is running or required, set the current basal as a temp, so you can see on the pump that the loop is working
                if ((!temps_data.duration || (temps_data.rate == profile_data.current_basal)) && !requestedTemp.duration) {
                    reason = reason + "; setting current basal of " + profile_data.current_basal + " as temp";
                    setTempBasal(profile_data.current_basal, 30);
                }
            }
        }  else {
            reason = "CGM is calibrating or in ??? state";
            console.error(reason);
        }
    } else {
        reason = "BG data is too old";
        console.error(reason);
    }


requestedTemp.reason = reason;    
console.log(JSON.stringify(requestedTemp));
}
