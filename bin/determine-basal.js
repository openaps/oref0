#!/usr/bin/env node

function getLastGlucose(data) {
    
    var one = data[0];
    var two = data[1];
    var o = {
        delta: one.glucose - two.glucose
        , glucose: one.glucose
    };
    
    return o;
    
}

function setTempBasal(rate, duration) {
    
    maxSafeBasal = Math.min(profile_data.max_basal, 2 * profile_data.max_daily_basal, 4 * profile_data.current_basal);
    
    if (rate < 0) { rate = 0; }         
    
    else if (rate > maxSafeBasal) { rate = maxSafeBasal; }
    
    requestedTemp.duration = duration;
    requestedTemp.rate = rate;
    
};

    
if (!module.parent) {
    var iob_input = process.argv.slice(2, 3).pop()
    var temps_input = process.argv.slice(3, 4).pop()
    var glucose_input = process.argv.slice(4, 5).pop()
    var profile_input = process.argv.slice(5, 6).pop()
    
    if (!iob_input || !temps_input || !glucose_input || !profile_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<iob.json> <current-temps.json> <glucose.json> <profile.json>');
        process.exit(1);
    }
    
    var cwd = process.cwd()
    var glucose_data = require(cwd + '/' + glucose_input);
    var temps_data = require(cwd + '/' + temps_input);
    var iob_data = require(cwd + '/' + iob_input);
    var profile_data = require(cwd + '/' + profile_input);
    
    var glucose_status = getLastGlucose(glucose_data);
    var bg = glucose_status.glucose
    var eventualBG = bg - (iob_data.iob * profile_data.sens);
    var requestedTemp = {
        'temp': 'absolute'
    };
    
    
        
    //if old reading from Dexcom do nothing
    
    var systemTime = new Date();
    var displayTime = new Date(glucose_data[0].display_time.replace('T', ' '));
    var minAgo = (systemTime - displayTime) / 60 / 1000
    
    if (minAgo < 10 && minAgo > -5 ) { // Dexcom data is recent, but not far in the future

        if (bg < profile_data.min_bg - 30) { // low glucose suspend mode: BG is < ~80
            if (glucose_status.delta > 0) { // if BG is rising
                if (temps_data.rate > profile_data.current_basal) { // if a high-temp is running
                    setTempBasal(0, 0); // cancel it
                }
            }
            else { // if (glucose_status.delta <= 0) { // BG is not yet rising
                setTempBasal(0, 30);
            }
            

        } else {
            
            if ((glucose_status.delta > 0 && eventualBG < profile_data.min_bg) || (glucose_status.delta < 0 && eventualBG >= profile_data.max_bg)) {
                // cancel temp
                setTempBasal(0, 0);
        
            } else if (eventualBG < profile_data.min_bg) {
                
                var insulinReq = Math.max(0, (profile_data.target_bg - eventualBG) / profile_data.sens);
                var rate = temps_data.rate - (2 * insulinReq);
                setTempBasal(rate, 30);
        

            } else if (eventualBG > profile_data.max_bg) {
                var insulinReq = (profile_data.target_bg - eventualBG) / profile_data.sens;
                var rate = temps_data.rate - (2 * insulinReq);
                if (rate > temps_data.rate){
                    setTempBasal(rate, 30);
                }
        
            } else {
                console.log("No action required")
            }
        }
    } else {
        console.log("BG data is too old")
    }
    
    console.log(JSON.stringify(requestedTemp));
}




