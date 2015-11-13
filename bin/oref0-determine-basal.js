#!/usr/bin/env node

/*
  Determine Basal

  Released under MIT license. See the accompanying LICENSE.txt file for
  full terms and conditions

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
*/

if (!module.parent) {
    var determinebasal = init();

    var iob_input = process.argv.slice(2, 3).pop();
    var currenttemp_input = process.argv.slice(3, 4).pop();
    var glucose_input = process.argv.slice(4, 5).pop();
    var profile_input = process.argv.slice(5, 6).pop();
    var offline = process.argv.slice(6, 7).pop();

    if (!iob_input || !currenttemp_input || !glucose_input || !profile_input) {
        console.error('usage: ', process.argv.slice(0, 2), '<iob.json> <currenttemp.json> <glucose.json> <profile.json> [Offline]');
        process.exit(1);
    }
    
    var cwd = process.cwd();
    var glucose_data = require(cwd + '/' + glucose_input);
    var currenttemp = require(cwd + '/' + currenttemp_input);
    var iob_data = require(cwd + '/' + iob_input);
    var profile = require(cwd + '/' + profile_input);
    var glucose_status = determinebasal.getLastGlucose(glucose_data);

    //if old reading from Dexcom do nothing

    var systemTime = new Date();
    var bgTime;
    if (glucose_data[0].display_time) {
        bgTime = new Date(glucose_data[0].display_time.replace('T', ' '));
    } else if (glucose_data[0].dateString) {
        bgTime = new Date(glucose_data[0].dateString);
    } else { console.error("Could not determine last BG time"); }
    var minAgo = (systemTime - bgTime) / 60 / 1000;

    if (minAgo > 10 || minAgo < -5) { // Dexcom data is too old, or way in the future
        var reason = "BG data is too old, or clock set incorrectly";
        console.error(reason);
        return 1;
    }
    console.error(JSON.stringify(glucose_status));
    console.error(JSON.stringify(currenttemp));
    console.error(JSON.stringify(iob_data));
    console.error(JSON.stringify(profile));
    rT = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);

}
    
function init() {

    var determinebasal = {
        name: 'determine-basal'
        , label: "OpenAPS Determine Basal"
        , pluginType: 'pill-major'
    };

    determinebasal.getLastGlucose = function getLastGlucose(data) {

        data = data.map(function prepGlucose (obj) {
            //Support the NS sgv field to avoid having to convert in a custom way
            obj.glucose = obj.glucose || obj.sgv;
            return obj;
        });

        var now = data[0];
        var last = data[1];
        var minutes;
        var change;
        var avg;

        //TODO: calculate average using system_time instead of assuming 1 data point every 5m
        if (typeof data[3] !== 'undefined' && data[3].glucose > 30) {
            minutes = 3*5;
            change = now.glucose - data[3].glucose;
        } else if (typeof data[2] !== 'undefined' && data[2].glucose > 30) {
            minutes = 2*5;
            change = now.glucose - data[2].glucose;
        } else if (typeof last !== 'undefined' && last.glucose > 30) {
            minutes = 5;
            change = now.glucose - last.glucose;
        } else { change = 0; }
        // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
        avg = change/minutes * 5;

        return {
            delta: now.glucose - last.glucose
            , glucose: now.glucose
            , avgdelta: avg
        };
    };


    determinebasal.determine_basal = function determine_basal(glucose_status, currenttemp, iob_data, profile, offline) {
        if (typeof profile === 'undefined' || typeof profile.current_basal === 'undefined') {
            console.error('Error: could not get current basal rate');
            process.exit(1);
        }

        var max_iob = profile.max_iob; // maximum amount of non-bolus IOB OpenAPS will ever deliver

        // if target_bg is set, great. otherwise, if min and max are set, then set target to their average
        var target_bg;
        if (typeof profile.target_bg !== 'undefined') {
            target_bg = profile.target_bg;
        } else {
            if (typeof profile.max_bg !== 'undefined' && typeof profile.max_bg !== 'undefined') {
                target_bg = (profile.min_bg + profile.max_bg) / 2;
            } else {
                console.error('Error: could not determine target_bg');
                process.exit(1);
            }
        }
        
        var bg = glucose_status.glucose;
        var tick;
        if (glucose_status.delta >= 0) { tick = "+" + glucose_status.delta; }
        else { tick = glucose_status.delta; }
        console.error("IOB: " + iob_data.iob.toFixed(2) + ", Bolus IOB: " + iob_data.bolusiob.toFixed(2));
        //calculate BG impact: the amount BG "should" be rising or falling based on insulin activity alone
        var bgi = Math.round(( -iob_data.activity * profile.sens * 5 )*100)/100;
        console.error("Avg. Delta: " + glucose_status.avgdelta.toFixed(1) + ", BGI: " + bgi.toFixed(1));
        // project deviation over next 15 minutes
        var deviation = Math.round( 15 / 5 * ( glucose_status.avgdelta - bgi ) );
        console.error("15m deviation: " + deviation.toFixed(0));
        // calculate the naive (bolus calculator math) eventual BG based on net IOB and sensitivity
        var naive_eventualBG = Math.round( bg - (iob_data.iob * profile.sens) );
        // and adjust it for the deviation above
        var eventualBG = naive_eventualBG + deviation;
        // calculate what portion of that is due to bolusiob
        var bolusContrib = iob_data.bolusiob * profile.sens;
        // and add it back in to get snoozeBG, plus another 50% to avoid low-temping at mealtime
        var naive_snoozeBG = Math.round( naive_eventualBG + 1.5 * bolusContrib );
        // adjust that for deviation like we did eventualBG
        var snoozeBG = naive_snoozeBG + deviation;
        console.error("BG: " + bg + tick + " -> " + eventualBG + "-" + snoozeBG + " (Unadjusted: " + naive_eventualBG + "-" + naive_snoozeBG + ")");
        if (typeof eventualBG === 'undefined') { console.error('Error: could not calculate eventualBG'); }
        var rT = { //short for requestedTemp
            'temp': 'absolute'
            , 'bg': bg
            , 'tick': tick
            , 'eventualBG': eventualBG
            , 'snoozeBG': snoozeBG
        };
        
        
        if (bg < 30) {  //Dexcom is in ??? mode or calibrating, do nothing. Asked @benwest for raw data in iter_glucose
            rT.reason = "CGM is calibrating or in ??? state";
            console.error(rT.reason);
            console.log(JSON.stringify(rT));
            return rT;
        }
        var threshold = profile.min_bg - 30;
        
        if (bg < threshold) { // low glucose suspend mode: BG is < ~80
            rT.reason = "BG " + bg + "<" + threshold;
            if ((glucose_status.delta < 0 && glucose_status.avgdelta < 0) || (glucose_status.delta < bgi && glucose_status.avgdelta < bgi)) {
                // BG is still falling / rising slower than predicted
                console.error(rT.reason);
                return determinebasal.setTempBasal(0, 30, profile, rT, offline);
            }
            if (glucose_status.delta > glucose_status.avgdelta) {
                rT.reason += ", delta " + glucose_status.delta + ">0";
            } else {
                rT.reason += ", avg delta " + glucose_status.avgdelta + ">0";
            }
            if (currenttemp.rate > profile.current_basal) { // if a high-temp is running
                return determinebasal.setTempBasal(0, 0, profile, rT, offline); // cancel high temp
            } else if (currenttemp.duration && eventualBG > profile.max_bg) { // if low-temped and predicted to go high from negative IOB
                return determinebasal.setTempBasal(0, 0, profile, rT, offline); // cancel low temp
            }
            rT.reason += "; no high-temp to cancel";
            console.error(rT.reason);
            console.log(JSON.stringify(rT));
            return rT;
        } 
        if (eventualBG < profile.min_bg) { // if eventual BG is below target:
            rT.reason = "Eventual BG " + eventualBG + "<" + profile.min_bg;
            // if 5m or 15m avg BG is rising faster than BGI/2
            if (glucose_status.delta > bgi/2 && glucose_status.avgdelta > bgi/2) {
                rT.reason += ", but Delta " + tick + " > BGI " + bgi + " / 2";
                if (currenttemp.duration > 0) { // if there is currently any temp basal running
                    rT.reason = rT.reason += "; cancel";
                    return determinebasal.setTempBasal(0, 0, profile, rT, offline); // cancel temp
                }
                rT.reason = rT.reason += "; no temp to cancel";
                console.error(rT.reason);
                console.log(JSON.stringify(rT));
                return rT;
            }
            // if this is just due to boluses, we can snooze until the bolus IOB decays (at double speed)
            if (snoozeBG > profile.min_bg) { // if adding back in the bolus contribution BG would be above min
                // if BG is falling and high-temped, or rising and low-temped, cancel
                // compare against zero here, not BGI, because BGI will be highly negative from boluses and no carbs
                if (glucose_status.delta < 0 && currenttemp.rate > profile.current_basal) {
                    rT.reason += tick + ", and temp " + currenttemp.rate + " > basal " + profile.current_basal;
                    return determinebasal.setTempBasal(0, 0, profile, rT, offline); // cancel temp
                } else if (glucose_status.delta > 0 && currenttemp.rate < profile.current_basal) {
                    rT.reason += tick + ", and temp " + currenttemp.rate + " < basal " + profile.current_basal;
                    return determinebasal.setTempBasal(0, 0, profile, rT, offline); // cancel temp
                }
                rT.reason += "bolus snooze: eventual BG range " + eventualBG + "-" + snoozeBG;
                console.error(rT.reason);
                console.log(JSON.stringify(rT));
                return rT;
            }
            // calculate 30m low-temp required to get projected BG up to target
            // use snoozeBG instead of eventualBG to more gradually ramp in any counteraction of the user's boluses
            var insulinReq = Math.min(0, (snoozeBG - target_bg) / profile.sens);
            // rate required to deliver insulinReq less insulin over 30m:
            var rate = profile.current_basal + (2 * insulinReq);
            rate = Math.round( rate * 1000 ) / 1000;
            // if required temp < existing temp basal
            if (typeof currenttemp.rate !== 'undefined' && (currenttemp.duration > 0 && rate > currenttemp.rate - 0.1)) {
                rT.reason += "temp " + currenttemp.rate + " <~ req " + rate + "U/hr";
                console.error(rT.reason);
                console.log(JSON.stringify(rT));
                return rT;
            }
            rT.reason += ", no temp, setting " + rate + "U/hr";
            return determinebasal.setTempBasal(rate, 30, profile, rT, offline);
        }
        // if eventual BG is above min but BG is falling faster than BGI/2
        if (glucose_status.delta < bgi/2 || glucose_status.avgdelta < bgi/2) {
            rT.reason = "Eventual BG " + eventualBG + ">" + profile.min_bg + " but Delta " + tick + " < BGI " + bgi + " / 2";
            if (currenttemp.duration > 0) { // if there is currently any temp basal running
                rT.reason = rT.reason += "; cancel";
                return determinebasal.setTempBasal(0, 0, profile, rT, offline); // cancel temp
            }
            rT.reason = rT.reason += "; no temp to cancel";
            console.error(rT.reason);
            console.log(JSON.stringify(rT));
            return rT;
        }
        if (eventualBG < profile.max_bg) {
            rT.reason = eventualBG + " is in range. No temp required";
            if (currenttemp.duration > 0) { // if there is currently any temp basal running
                return determinebasal.setTempBasal(0, 0, profile, rT, offline); // cancel temp
            }
            if (offline == 'Offline') {
                // if no temp is running or required, set the current basal as a temp, so you can see on the pump that the loop is working
                if ((!currenttemp.duration || (currenttemp.rate == profile.current_basal)) && !rT.duration) {
                    rT.reason = rT.reason + "; setting current basal of " + profile.current_basal + " as temp";
                    return determinebasal.setTempBasal(profile.current_basal, 30, profile, rT, offline);
                }
            }
            console.error(rT.reason);
            console.log(JSON.stringify(rT));
            return rT;
        }

        // eventual BG is above target:
        // if iob is over max, just cancel any temps
        var basal_iob = Math.round(( iob_data.iob - iob_data.bolusiob )*1000)/1000;
        rT.reason = "Eventual BG " + eventualBG + ">" + profile.max_bg + ", ";
        if (basal_iob > max_iob) {
            rT.reason = "basal_iob " + basal_iob + " > max_iob " + max_iob;
            return determinebasal.setTempBasal(0, 0, profile, rT, offline);
        }
        // otherwise, calculate 30m high-temp required to get projected BG down to target
        // insulinReq is the additional insulin required to get down to max bg:
        var insulinReq = (eventualBG - target_bg) / profile.sens;
        // if that would put us over max_iob, then reduce accordingly
        if (insulinReq > max_iob-basal_iob) {
            rT.reason = "max_iob " + max_iob + ", ";
            insulinReq = max_iob-basal_iob;
        }

        // rate required to deliver insulinReq more insulin over 30m:
        var rate = profile.current_basal + (2 * insulinReq);
        rate = Math.round( rate * 1000 ) / 1000;

        maxSafeBasal = Math.min(profile.max_basal, 3 * profile.max_daily_basal, 4 * profile.current_basal);
        if (rate > maxSafeBasal) {
            rate = maxSafeBasal;
        }
        var insulinScheduled = currenttemp.duration * (currenttemp.rate - profile.current_basal) / 60;
        if (insulinScheduled > insulinReq + 0.3) { // if current temp would deliver >0.3U more than the required insulin, lower the rate
            rT.reason = currenttemp.duration + "@" + currenttemp.rate + " > req " + insulinReq + "U";
            return determinebasal.setTempBasal(rate, 30, profile, rT, offline);
        }
        if (typeof currenttemp.rate == 'undefined' || currenttemp.rate == 0) { // no temp is set
            rT.reason += "no temp, setting " + rate + "U/hr";
            return determinebasal.setTempBasal(rate, 30, profile, rT, offline);
        }
        if (currenttemp.duration > 0 && rate < currenttemp.rate + 0.1) { // if required temp <~ existing temp basal
            rT.reason += "temp " + currenttemp.rate + " >~ req " + rate + "U/hr";
            console.error(rT.reason);
            console.log(JSON.stringify(rT));
            return rT;
        } // required temp > existing temp basal
        rT.reason += "temp " + currenttemp.rate + "<" + rate + "U/hr";
        return determinebasal.setTempBasal(rate, 30, profile, rT, offline);

        
    };

    determinebasal.setTempBasal = function setTempBasal(rate, duration, profile, rT, offline) {
        
        maxSafeBasal = Math.min(profile.max_basal, 3 * profile.max_daily_basal, 4 * profile.current_basal);
        
        if (rate < 0) { rate = 0; } // if >30m @ 0 required, zero temp will be extended to 30m instead
        else if (rate > maxSafeBasal) { rate = maxSafeBasal; }
        
        // rather than canceling temps, if Offline mode is set, always set the current basal as a 30m temp
        // so we can see on the pump that openaps is working
        if (duration == 0 && offline == 'Offline') {
            rate = profile.current_basal;
            duration  = 30;
        }

        rT.duration = duration;
        rT.rate = Math.round((Math.round(rate / 0.05) * 0.05)*100)/100;
        console.log(JSON.stringify(rT));
        return rT;
    };

    return determinebasal;

}
module.exports = init;
