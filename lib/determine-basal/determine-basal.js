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


var round_basal = require('../round-basal')

// Rounds value to 'digits' decimal places
function round(value, digits)
{
    if (! digits) { digits = 0; }
    var scale = Math.pow(10, digits);
    return Math.round(value * scale) / scale;
}

// we expect BG to rise or fall at the rate of BGI,
// adjusted by the rate at which BG would need to rise /
// fall to get eventualBG to target over DIA/2 hours
function calculate_expected_delta(dia, target_bg, eventual_bg, bgi) {
    // (hours * mins_per_hour) / 5 = how many 5 minute periods in dia/2
    var dia_in_5min_blocks = (dia/2 * 60) / 5;
    var target_delta = target_bg - eventual_bg;
    var expectedDelta = round(bgi + (target_delta / dia_in_5min_blocks), 1);
    return expectedDelta;
}


function convert_bg(value, profile)
{
    if (profile.out_units == "mmol/L")
    {
        return round(value / 18, 1).toFixed(1);
    }
    else
    {
        return value.toFixed(0);
    }
}

var determine_basal = function determine_basal(glucose_status, currenttemp, iob_data, profile, autosens_data, meal_data, tempBasalFunctions, microBolusAllowed, reservoir_data) {
    var rT = {}; //short for requestedTemp

    if (typeof profile === 'undefined' || typeof profile.current_basal === 'undefined') {
        rT.error ='Error: could not get current basal rate';
        return rT;
    }
    var basal = profile.current_basal;
    if (typeof autosens_data !== 'undefined' ) {
        basal = profile.current_basal * autosens_data.ratio;
        basal = round_basal(basal, profile);
        if (basal != profile.current_basal) {
            process.stderr.write("Autosens adjusting basal from "+profile.current_basal+" to "+basal+"; ");
        } else {
            process.stderr.write("Basal unchanged: "+basal+"; ");
        }
    }

    var bg = glucose_status.glucose;
    if (bg < 39) {  //Dexcom is in ??? mode or calibrating
        rT.reason = "CGM is calibrating or in ??? state";
        if (basal <= currenttemp.rate * 1.2) { // high temp is running
            rT.reason += "; setting current basal of " + basal + " as temp";
            return tempBasalFunctions.setTempBasal(basal, 30, profile, rT, currenttemp);
        } else { //do nothing.
            rT.reason += ", temp " + currenttemp.rate + " <~ current basal " + basal + "U/hr";
            return rT;
        }
    }

    var max_iob = profile.max_iob; // maximum amount of non-bolus IOB OpenAPS will ever deliver

    // if target_bg is set, great. otherwise, if min and max are set, then set target to their average
    var target_bg;
    var min_bg;
    var max_bg;
    if (typeof profile.min_bg !== 'undefined') {
            min_bg = profile.min_bg;
    }
    if (typeof profile.max_bg !== 'undefined') {
            max_bg = profile.max_bg;
    }
    if (typeof profile.target_bg !== 'undefined') {
        target_bg = profile.target_bg;
    } else {
        if (typeof profile.min_bg !== 'undefined' && typeof profile.max_bg !== 'undefined') {
            target_bg = (profile.min_bg + profile.max_bg) / 2;
        } else {
            rT.error ='Error: could not determine target_bg';
            return rT;
        }
    }

    // adjust min, max, and target BG for sensitivity, such that 50% increase in ISF raises target from 100 to 120
    if (typeof autosens_data !== 'undefined' && profile.autosens_adjust_targets) {
      if (profile.temptargetSet) {
        process.stderr.write("Temp Target set, not adjusting with autosens; ");
      } else {
        min_bg = round((min_bg - 60) / autosens_data.ratio) + 60;
        max_bg = round((max_bg - 60) / autosens_data.ratio) + 60;
        new_target_bg = round((target_bg - 60) / autosens_data.ratio) + 60;
        if (target_bg == new_target_bg) {
            process.stderr.write("target_bg unchanged: "+new_target_bg+"; ");
        } else {
            process.stderr.write("target_bg from "+target_bg+" to "+new_target_bg+"; ");
        }
        target_bg = new_target_bg;
      }
    }

    if (typeof iob_data === 'undefined' ) {
        rT.error ='Error: iob_data undefined';
        return rT;
    }

    var iobArray = iob_data;
    if (typeof(iob_data.length) && iob_data.length > 1) {
        iob_data = iobArray[0];
        //console.error(JSON.stringify(iob_data[0]));
    }

    if (typeof iob_data.activity === 'undefined' || typeof iob_data.iob === 'undefined' ) {
        rT.error ='Error: iob_data missing some property';
        return rT;
    }

    var tick;

    if (glucose_status.delta > -0.5) {
        tick = "+" + round(glucose_status.delta,0);
    } else {
        tick = round(glucose_status.delta,0);
    }
    var minDelta = Math.min(glucose_status.delta, glucose_status.short_avgdelta, glucose_status.long_avgdelta);
    var minAvgDelta = Math.min(glucose_status.short_avgdelta, glucose_status.long_avgdelta);

    var sens = profile.sens;
    if (typeof autosens_data !== 'undefined' ) {
        sens = profile.sens / autosens_data.ratio;
        sens = round(sens, 1);
        if (sens != profile.sens) {
            process.stderr.write("sens from "+profile.sens+" to "+sens);
        } else {
            process.stderr.write("sens unchanged: "+sens);
        }
    }
    console.error("");

    //calculate BG impact: the amount BG "should" be rising or falling based on insulin activity alone
    var bgi = round(( -iob_data.activity * sens * 5 ), 2);
    // project deviations for 30 minutes
    var deviation = round( 30 / 5 * ( minDelta - bgi ) );
    // don't overreact to a big negative delta: use minAvgDelta if deviation is negative
    if (deviation < 0) {
        deviation = round( (30 / 5) * ( minAvgDelta - bgi ) );
    }

    // calculate the naive (bolus calculator math) eventual BG based on net IOB and sensitivity
    if (iob_data.iob > 0) {
        var naive_eventualBG = round( bg - (iob_data.iob * sens) );
    } else { // if IOB is negative, be more conservative and use the lower of sens, profile.sens
        var naive_eventualBG = round( bg - (iob_data.iob * Math.min(sens, profile.sens) ) );
    }
    // and adjust it for the deviation above
    var eventualBG = naive_eventualBG + deviation;
    // calculate what portion of that is due to bolussnooze
    var bolusContrib = iob_data.bolussnooze * sens;
    // and add it back in to get snoozeBG, plus another 50% to avoid low-temping at mealtime
    var naive_snoozeBG = round( naive_eventualBG + 1.5 * bolusContrib );
    // adjust that for deviation like we did eventualBG
    var snoozeBG = naive_snoozeBG + deviation;

    // adjust target BG range if needed to safely bring down high BG faster without causing lows
    if ( bg > max_bg && profile.adjust_targets_when_high ) {
        // with target=100, as BG rises from 100 to 160, adjustedTarget drops from 100 to 80
        var adjustedMinBG = round(Math.max(80, min_bg - (bg - min_bg)/3 ),0);
        var adjustedTargetBG =round( Math.max(80, target_bg - (bg - target_bg)/3 ),0);
        var adjustedMaxBG = round(Math.max(80, max_bg - (bg - max_bg)/3 ),0);
        // if eventualBG, naive_eventualBG, and target_bg aren't all above adjustedMinBG, don’t use it
        console.error("naive_eventualBG:",naive_eventualBG+", eventualBG:",eventualBG);
        if (eventualBG > adjustedMinBG && naive_eventualBG > adjustedMinBG && min_bg > adjustedMinBG) {
            process.stderr.write("Adjusting targets for high BG: min_bg from "+min_bg+" to "+adjustedMinBG+"; ");
            min_bg = adjustedMinBG;
        } else {
            process.stderr.write("min_bg unchanged: "+min_bg+"; ");
        }
        // if eventualBG, naive_eventualBG, and target_bg aren't all above adjustedTargetBG, don’t use it
        if (eventualBG > adjustedTargetBG && naive_eventualBG > adjustedTargetBG && target_bg > adjustedTargetBG) {
            process.stderr.write("target_bg from "+target_bg+" to "+adjustedTargetBG+"; ");
            target_bg = adjustedTargetBG;
        } else {
            process.stderr.write("target_bg unchanged: "+target_bg+"; ");
        }
        // if eventualBG, naive_eventualBG, and max_bg aren't all above adjustedMaxBG, don’t use it
        if (eventualBG > adjustedMaxBG && naive_eventualBG > adjustedMaxBG && max_bg > adjustedMaxBG) {
            console.error("max_bg from "+max_bg+" to "+adjustedMaxBG);
            max_bg = adjustedMaxBG;
        } else {
            console.error("max_bg unchanged: "+max_bg);
        }
    }

    var expectedDelta = calculate_expected_delta(profile.dia, target_bg, eventualBG, bgi);
    if (typeof eventualBG === 'undefined' || isNaN(eventualBG)) {
        rT.error ='Error: could not calculate eventualBG';
        return rT;
    }

    // min_bg of 90 -> threshold of 70, 110 -> 80, and 130 -> 90
    var threshold = min_bg - 0.5*(min_bg-50);

    //console.error(reservoir_data);
    var deliverAt = new Date();

    rT = {
        'temp': 'absolute'
        , 'bg': bg
        , 'tick': tick
        , 'eventualBG': eventualBG
        , 'snoozeBG': snoozeBG
        , 'insulinReq': 0
        , 'reservoir' : reservoir_data // The expected reservoir volume at which to deliver the microbolus (the reservoir volume from immediately before the last pumphistory run)
        , 'deliverAt' : deliverAt // The time at which the microbolus should be delivered
    };

    var basaliob;
    if (iob_data.basaliob) { basaliob = iob_data.basaliob; }
    else { basaliob = iob_data.iob - iob_data.bolussnooze; }

    // generate predicted future BGs based on IOB, COB, and current absorption rate

    var COBpredBGs = [];
    var aCOBpredBGs = [];
    var IOBpredBGs = [];
    COBpredBGs.push(bg);
    aCOBpredBGs.push(bg);
    IOBpredBGs.push(bg);
    //console.error(meal_data);
    // carb impact and duration are 0 unless changed below
    var ci = 0;
    var cid = 0;
    // calculate current carb absorption rate, and how long to absorb all carbs
    // CI = current carb impact on BG in mg/dL/5m
    ci = round((minDelta - bgi),1);
    if (meal_data.mealCOB * 3 > meal_data.carbs) {
        // set ci to a minimum of 3mg/dL/5m (default) if at least 1/3 of carbs from the last DIA hours are still unabsorbed
        ci = Math.max(profile.min_5m_carbimpact, ci);
    }
    aci = 10;
    //5m data points = g * (1U/10g) * (40mg/dL/1U) / (mg/dL/5m)
    cid = meal_data.mealCOB * ( sens / profile.carb_ratio ) / ci;
    acid = meal_data.mealCOB * ( sens / profile.carb_ratio ) / aci;
    console.error("Carb Impact:",ci,"mg/dL per 5m; CI Duration:",round(cid/6,1),"hours");
    console.error("Accel. Carb Impact:",aci,"mg/dL per 5m; ACI Duration:",round(acid/6,1),"hours");
    var minPredBG = 999;
    var maxPredBG = bg;
    var eventualPredBG = bg;
    try {
        iobArray.forEach(function(iobTick) {
            //console.error(iobTick);
            predBGI = round(( -iobTick.activity * sens * 5 ), 2);
            // predicted deviation impact drops linearly from current deviation down to zero
            // over 60 minutes (data points every 5m)
            predDev = ci * ( 1 - Math.min(1,IOBpredBGs.length/(60/5)) );
            IOBpredBG = IOBpredBGs[IOBpredBGs.length-1] + predBGI + predDev;
            //IOBpredBG = IOBpredBGs[IOBpredBGs.length-1] + predBGI;
            // predicted carb impact drops linearly from current carb impact down to zero
            // eventually accounting for all carbs (if they can be absorbed over DIA)
            predCI = Math.max(0, ci * ( 1 - COBpredBGs.length/Math.max(cid*2,1) ) );
            predACI = Math.max(0, aci * ( 1 - COBpredBGs.length/Math.max(acid*2,1) ) );
            COBpredBG = COBpredBGs[COBpredBGs.length-1] + predBGI + Math.min(0,predDev) + predCI;
            aCOBpredBG = aCOBpredBGs[aCOBpredBGs.length-1] + predBGI + Math.min(0,predDev) + predACI;
            //console.error(predBGI, predCI, predBG);
            IOBpredBGs.push(IOBpredBG);
            COBpredBGs.push(COBpredBG);
            aCOBpredBGs.push(aCOBpredBG);
            // wait 45m before setting minPredBG
            if ( COBpredBGs.length > 9 && (COBpredBG < minPredBG) ) { minPredBG = COBpredBG; }
            if ( COBpredBG > maxPredBG ) { maxPredBG = COBpredBG; }
        });
        // set eventualBG to include effect of carbs
        //console.error("PredBGs:",JSON.stringify(predBGs));
    } catch (e) {
        console.error("Problem with iobArray.  Optional feature Advanced Meal Assist disabled.");
    }
    rT.predBGs = {};
    IOBpredBGs.forEach(function(p, i, theArray) {
        theArray[i] = round(Math.min(401,Math.max(39,p)));
    });
    for (var i=IOBpredBGs.length-1; i > 12; i--) {
        if (IOBpredBGs[i-1] != IOBpredBGs[i]) { break; }
        else { IOBpredBGs.pop(); }
    }
    rT.predBGs.IOB = IOBpredBGs;
    if (meal_data.mealCOB > 0) {
        aCOBpredBGs.forEach(function(p, i, theArray) {
            theArray[i] = round(Math.min(401,Math.max(39,p)));
        });
        for (var i=aCOBpredBGs.length-1; i > 12; i--) {
            if (aCOBpredBGs[i-1] != aCOBpredBGs[i]) { break; }
            else { aCOBpredBGs.pop(); }
        }
        rT.predBGs.aCOB = aCOBpredBGs;
    }
    if (meal_data.mealCOB > 0 && ci > 0 ) {
        COBpredBGs.forEach(function(p, i, theArray) {
            theArray[i] = round(Math.min(401,Math.max(39,p)));
        });
        for (var i=COBpredBGs.length-1; i > 12; i--) {
            if (COBpredBGs[i-1] != COBpredBGs[i]) { break; }
            else { COBpredBGs.pop(); }
        }
        rT.predBGs.COB = COBpredBGs;
        eventualBG = Math.max(eventualBG, round(COBpredBGs[COBpredBGs.length-1]) );
        rT.eventualBG = eventualBG;
        minPredBG = Math.min(minPredBG, eventualBG);
        // set snoozeBG to minPredBG
        snoozeBG = round(Math.max(snoozeBG,minPredBG));
        rT.snoozeBG = snoozeBG;
    }

    rT.COB=meal_data.mealCOB;
    rT.IOB=iob_data.iob;
    rT.reason="COB: " + meal_data.mealCOB + ", Dev: " + deviation + ", BGI: " + bgi + ", ISF: " + convert_bg(sens, profile) + ", Target: " + convert_bg(target_bg, profile) + "; ";
    if (bg < threshold) { // low glucose suspend mode: BG is < ~80
        rT.reason += "BG " + convert_bg(bg, profile) + "<" + convert_bg(threshold, profile);
        if ((glucose_status.delta <= 0 && minDelta <= 0) || (glucose_status.delta < expectedDelta && minDelta < expectedDelta) || bg < 60 ) {
            // BG is still falling / rising slower than predicted
            return tempBasalFunctions.setTempBasal(0, 30, profile, rT, currenttemp);
        }
        if (glucose_status.delta > minDelta) {
            rT.reason += ", delta " + glucose_status.delta + ">0";
        } else {
            rT.reason += ", min delta " + minDelta.toFixed(2) + ">0";
        }
        if (currenttemp.duration > 15 && (round_basal(basal, profile) === round_basal(currenttemp.rate, profile))) {
            rT.reason += ", temp " + currenttemp.rate + " ~ req " + basal + "U/hr";
            return rT;
        } else {
            rT.reason += "; setting current basal of " + basal + " as temp";
            return tempBasalFunctions.setTempBasal(basal, 30, profile, rT, currenttemp);
        }
    }

    if (eventualBG < min_bg) { // if eventual BG is below target:
        rT.reason += "Eventual BG " + convert_bg(eventualBG, profile) + " < " + convert_bg(min_bg, profile);
        // if 5m or 30m avg BG is rising faster than expected delta
        if (minDelta > expectedDelta && minDelta > 0) {
            if (glucose_status.delta > minDelta) {
                rT.reason += ", but Delta " + tick + " > Exp. Delta " + expectedDelta;
            } else {
                rT.reason += ", but Min. Delta " + minDelta.toFixed(2) + " > Exp. Delta " + expectedDelta;
            }
            if (currenttemp.duration > 15 && (round_basal(basal, profile) === round_basal(currenttemp.rate, profile))) {
                rT.reason += ", temp " + currenttemp.rate + " ~ req " + basal + "U/hr";
                return rT;
            } else {
                rT.reason += "; setting current basal of " + basal + " as temp";
                return tempBasalFunctions.setTempBasal(basal, 30, profile, rT, currenttemp);
            }
        }

        if (eventualBG < min_bg) {
            // if we've bolused recently, we can snooze until the bolus IOB decays (at double speed)
            if (snoozeBG > min_bg) { // if adding back in the bolus contribution BG would be above min
                // If we're in SMB mode, disable bolus snooze
                if (! (microBolusAllowed && ((profile.temptargetSet && target_bg < 100) || rT.COB))) {
                    rT.reason += ", bolus snooze: eventual BG range " + convert_bg(eventualBG, profile) + "-" + convert_bg(snoozeBG, profile);
                    //console.error(currenttemp, basal );
                    if (currenttemp.duration > 15 && (round_basal(basal, profile) === round_basal(currenttemp.rate, profile))) {
                        rT.reason += ", temp " + currenttemp.rate + " ~ req " + basal + "U/hr";
                        return rT;
                    } else {
                        rT.reason += "; setting current basal of " + basal + " as temp";
                        return tempBasalFunctions.setTempBasal(basal, 30, profile, rT, currenttemp);
                    }
                }
            } else {
                // calculate 30m low-temp required to get projected BG up to target
                // use snoozeBG to more gradually ramp in any counteraction of the user's boluses
                // multiply by 2 to low-temp faster for increased hypo safety
                var insulinReq = 2 * Math.min(0, (snoozeBG - target_bg) / sens);
                insulinReq = round( insulinReq , 2);
                if (minDelta < 0 && minDelta > expectedDelta) {
                    // if we're barely falling, newinsulinReq should be barely negative
                    rT.reason += ", Snooze BG " + convert_bg(snoozeBG, profile);
                    var newinsulinReq = round(( insulinReq * (minDelta / expectedDelta) ), 2);
                    //console.error("Increasing insulinReq from " + insulinReq + " to " + newinsulinReq);
                    insulinReq = newinsulinReq;
                }
                // rate required to deliver insulinReq less insulin over 30m:
                var rate = basal + (2 * insulinReq);
                rate = round_basal(rate, profile);
                // if required temp < existing temp basal
                var insulinScheduled = currenttemp.duration * (currenttemp.rate - basal) / 60;
                if (insulinScheduled < insulinReq - basal*0.3) { // if current temp would deliver a lot (30% of basal) less than the required insulin, raise the rate
                    rT.reason += ", "+currenttemp.duration + "m@" + (currenttemp.rate).toFixed(2) + " is a lot less than needed";
                    return tempBasalFunctions.setTempBasal(rate, 30, profile, rT, currenttemp);
                }
                if (typeof currenttemp.rate !== 'undefined' && (currenttemp.duration > 5 && rate >= currenttemp.rate * 0.8)) {
                    rT.reason += ", temp " + currenttemp.rate + " ~< req " + rate + "U/hr";
                    return rT;
                } else {
                    rT.reason += ", setting " + rate + "U/hr";
                    return tempBasalFunctions.setTempBasal(rate, 30, profile, rT, currenttemp);
                }
            }
        }
    }
  
    var minutes_running;
    if (typeof currenttemp.duration == 'undefined' || currenttemp.duration == 0) {
        minutes_running = 30;
    } else if (typeof currenttemp.minutesrunning !== 'undefined'){
        // If the time the current temp is running is not defined, use default request duration of 30 minutes.
        minutes_running = currenttemp.minutesrunning;
    } else {
        minutes_running = 30 - currenttemp.duration;
    }

    // if there is a low-temp running, and eventualBG would be below min_bg without it, let it run
    if (round_basal(currenttemp.rate, profile) < round_basal(basal, profile) ) {
        var lowtempimpact = (currenttemp.rate - basal) * ((30-minutes_running)/60) * sens;
        var adjEventualBG = eventualBG + lowtempimpact;
        // don't return early if microBolusAllowed etc.
        if ( adjEventualBG < min_bg && ! (microBolusAllowed && ((profile.temptargetSet && target_bg < 100) || rT.COB))) {
            rT.reason += "letting low temp of " + currenttemp.rate + " run.";
            return rT;
        }
    }

    // if eventual BG is above min but BG is falling faster than expected Delta
    if (minDelta < expectedDelta) {
        // if in SMB mode, don't cancel SMB zero temp
        if (! (microBolusAllowed && ((profile.temptargetSet && target_bg < 100) || rT.COB))) {
            if (glucose_status.delta < minDelta) {
                rT.reason += "Eventual BG " + convert_bg(eventualBG, profile) + " > " + convert_bg(min_bg, profile) + " but Delta " + tick + " < Exp. Delta " + expectedDelta;
            } else {
                rT.reason += "Eventual BG " + convert_bg(eventualBG, profile) + " > " + convert_bg(min_bg, profile) + " but Min. Delta " + minDelta.toFixed(2) + " < Exp. Delta " + expectedDelta;
            }
            if (currenttemp.duration > 15 && (round_basal(basal, profile) === round_basal(currenttemp.rate, profile))) {
                rT.reason += ", temp " + currenttemp.rate + " ~ req " + basal + "U/hr";
                return rT;
            } else {
                rT.reason += "; setting current basal of " + basal + " as temp";
                return tempBasalFunctions.setTempBasal(basal, 30, profile, rT, currenttemp);
            }
        }
    }
    // eventualBG, snoozeBG, or minPredBG is below max_bg
    if (Math.min(eventualBG,snoozeBG,minPredBG) < max_bg) {
        // if there is a high-temp running and eventualBG > max_bg, let it run
        if (eventualBG > max_bg && round_basal(currenttemp.rate, profile) > round_basal(basal, profile) ) {
            rT.reason += ", " + eventualBG + " > " + max_bg + ": no action required (letting high temp of " + currenttemp.rate + " run)."
            return rT;
        }

        // if in SMB mode, don't cancel SMB zero temp
        if (! (microBolusAllowed && ((profile.temptargetSet && target_bg < 100) || rT.COB))) {
            rT.reason += convert_bg(eventualBG, profile)+"-"+convert_bg(snoozeBG, profile)+" in range: no temp required";
            if (currenttemp.duration > 15 && (round_basal(basal, profile) === round_basal(currenttemp.rate, profile))) {
                rT.reason += ", temp " + currenttemp.rate + " ~ req " + basal + "U/hr";
                return rT;
            } else {
                rT.reason += "; setting current basal of " + basal + " as temp";
                return tempBasalFunctions.setTempBasal(basal, 30, profile, rT, currenttemp);
            }
        }
    }

    // eventual BG is at/above target:
    // if iob is over max, just cancel any temps
    var basaliob;
    if (iob_data.basaliob) { basaliob = iob_data.basaliob; }
    else { basaliob = iob_data.iob - iob_data.bolussnooze; }
    rT.reason += "Eventual BG " + convert_bg(eventualBG, profile) + " >= " +  convert_bg(max_bg, profile) + ", ";
    if (basaliob > max_iob) {
        rT.reason += "basaliob " + round(basaliob,2) + " > max_iob " + max_iob;
        if (currenttemp.duration > 15 && (round_basal(basal, profile) === round_basal(currenttemp.rate, profile))) {
            rT.reason += ", temp " + currenttemp.rate + " ~ req " + basal + "U/hr";
            return rT;
        } else {
            rT.reason += "; setting current basal of " + basal + " as temp";
            return tempBasalFunctions.setTempBasal(basal, 30, profile, rT, currenttemp);
        }
    } else { // otherwise, calculate 30m high-temp required to get projected BG down to target

        // insulinReq is the additional insulin required to get minPredBG down to target_bg
        var insulinReq = round( (Math.min(minPredBG,snoozeBG,eventualBG) - target_bg) / sens, 2);
        // when dropping, but not as fast as expected, reduce insulinReq proportionally
        // to the what fraction of expectedDelta we're dropping at
        if (minDelta < 0 && minDelta > expectedDelta) {
            var newinsulinReq = round(( insulinReq * (1 - (minDelta / expectedDelta)) ), 2);
            //console.error("Reducing insulinReq from " + insulinReq + " to " + newinsulinReq);
            insulinReq = newinsulinReq;
        }
        // if that would put us over max_iob, then reduce accordingly
        if (insulinReq > max_iob-basaliob) {
            rT.reason += "max_iob " + max_iob + ", ";
            insulinReq = max_iob-basaliob;
        }

        // rate required to deliver insulinReq more insulin over 30m:
        var rate = basal + (2 * insulinReq);
        rate = round_basal(rate, profile);
        insulinReq = round(insulinReq,3);
        rT.insulinReq = insulinReq;
        //console.error(iob_data.lastBolusTime);
        // minutes since last bolus
        var lastBolusAge = round(( new Date().getTime() - iob_data.lastBolusTime ) / 60000,1);
        //console.error(lastBolusAge);
        //console.error(profile.temptargetSet, target_bg, rT.COB);
        // only allow microboluses with COB or low temp targets
        // only microbolus if insulinReq represents 20m or more of basal
        if (microBolusAllowed && ((profile.temptargetSet && target_bg < 100) || rT.COB)) { // && insulinReq > profile.current_basal/3) {
            // never bolus more than 30m worth of basal
            maxBolus = profile.current_basal/2;
            // bolus 1/3 the insulinReq, up to maxBolus
            microBolus = round(Math.min(insulinReq/3,maxBolus),1);

            // calculate a long enough zero temp to eventually correct back up to target
            var smbTarget = target_bg;
            //var worstCaseInsulinReq = (smbTarget - naive_eventualBG) / sens + insulinReq/3;
            // only zero-temp for insulin already delivered, to help with intermittent pump comms
            var worstCaseInsulinReq = (smbTarget - naive_eventualBG) / sens;
            var durationReq = round(60*worstCaseInsulinReq / profile.current_basal);
            if (durationReq < 0) {
                durationReq = 0;
            // don't set a temp longer than 120 minutes
            } else {
                durationReq = round(durationReq/30)*30;
                durationReq = Math.min(120,Math.max(0,durationReq));
            }
            //console.error(durationReq);
            rT.reason += "insulinReq " + insulinReq + "; "
            if (durationReq < 0) {
                rT.reason += "setting " + durationReq + "m zero temp;"
            }

            var nextBolusMins = round(4-lastBolusAge,1);
            //console.error(naive_eventualBG, insulinReq, worstCaseInsulinReq, durationReq);
            console.error("naive_eventualBG",naive_eventualBG+",",durationReq+"m zero temp needed; last bolus",lastBolusAge+"m ago ("+iob_data.lastBolusTime+").");
            if (lastBolusAge > 4) {
                if (microBolus > 0) {
                    rT.units = microBolus;
                    rT.reason += "microbolusing " + microBolus + "U";
                }
            } else {
                rT.reason += "waiting " + nextBolusMins + "m to microbolus again";
            }
            rT.reason += ". ";

            // if no zero temp is required, don't return yet; allow later code to set a high temp
            if (durationReq > 0) {
                rT.rate = 0;
                rT.duration = durationReq;
                return rT;
            }
        }

        var maxSafeBasal = tempBasalFunctions.getMaxSafeBasal(profile);

        if (rate > maxSafeBasal) {
            rT.reason += "adj. req. rate: "+rate+" to maxSafeBasal: "+maxSafeBasal+", ";
            rate = round_basal(maxSafeBasal, profile);
        }

        var insulinScheduled = currenttemp.duration * (currenttemp.rate - basal) / 60;
        if (insulinScheduled >= insulinReq * 2) { // if current temp would deliver >2x more than the required insulin, lower the rate
            rT.reason += currenttemp.duration + "m@" + (currenttemp.rate).toFixed(2) + " > 2 * insulinReq. Setting temp basal of " + rate + "U/hr";
            return tempBasalFunctions.setTempBasal(rate, 30, profile, rT, currenttemp);
        }

        if (typeof currenttemp.duration == 'undefined' || currenttemp.duration == 0) { // no temp is set
            rT.reason += "no temp, setting " + rate + "U/hr";
            return tempBasalFunctions.setTempBasal(rate, 30, profile, rT, currenttemp);
        }

        if (currenttemp.duration > 5 && (round_basal(rate, profile) <= round_basal(currenttemp.rate, profile))) { // if required temp <~ existing temp basal
            rT.reason += "temp " + currenttemp.rate + " >~ req " + rate + "U/hr";
            return rT;
        }

        // required temp > existing temp basal
        rT.reason += "temp " + currenttemp.rate + "<" + rate + "U/hr";
        return tempBasalFunctions.setTempBasal(rate, 30, profile, rT, currenttemp);
    }

};

module.exports = determine_basal;
