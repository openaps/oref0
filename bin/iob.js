#!/usr/bin/env node

/*
  Insulin On Board (IOB) calculations.

  IOB is also known as "Bolus on Board", "Active Insulin", or "Insulin Remaining"

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

function iobCalc(treatment, time, dia) {
    var diaratio = dia / 3;
    var peak = 75 ;
    var end = 180 ;
    //var sens = profile_data.sens;
    if (typeof time === 'undefined') {
        var time = new Date();
    }

    if (treatment.insulin) {
        var bolusTime=new Date(treatment.date);
        var minAgo=(time-bolusTime)/1000/60 * diaratio;

        if (minAgo < 0) { 
            var iobContrib=0;
            var activityContrib=0;
        }
        else if (minAgo < peak) {
            var x = (minAgo/5 + 1);
            var iobContrib=treatment.insulin*(1-0.001852*x*x+0.001852*x);
            //var activityContrib=sens*treatment.insulin*(2/dia/60/peak)*minAgo;
            var activityContrib=treatment.insulin*(2/dia/60/peak)*minAgo;
        }
        else if (minAgo < end) {
            var x = (minAgo-peak)/5;
            var iobContrib=treatment.insulin*(0.001323*x*x - .054233*x + .55556);
            //var activityContrib=sens*treatment.insulin*(2/dia/60-(minAgo-peak)*2/dia/60/(60*dia-peak));
            var activityContrib=treatment.insulin*(2/dia/60-(minAgo-peak)*2/dia/60/(60*dia-peak));
        }
        else {
            var iobContrib=0;
            var activityContrib=0;
        }
        return {
            iobContrib: iobContrib,
            activityContrib: activityContrib
        };
    }
    else {
        return '';
    }
}
function iobTotal(treatments, time) {
    var iob = 0;
    var bolusiob = 0;
    var activity = 0;
    if (!treatments) return {};
    //if (typeof time === 'undefined') {
        //var time = new Date();
    //}

    treatments.forEach(function(treatment) {
        if(treatment.date < time.getTime( )) {
            var dia = profile_data.dia;
            var tIOB = iobCalc(treatment, time, dia);
            if (tIOB && tIOB.iobContrib) iob += tIOB.iobContrib;
            if (tIOB && tIOB.activityContrib) activity += tIOB.activityContrib;
            // keep track of bolus IOB separately for snoozes, but decay it three times as fast
            if (treatment.insulin >= 0.2 && treatment.started_at) {
                var bIOB = iobCalc(treatment, time, dia*2)
                //console.log(treatment);
                //console.log(bIOB);
                if (bIOB && bIOB.iobContrib) bolusiob += bIOB.iobContrib;
            }
        }
    });

    return {
        iob: iob,
        activity: activity,
        bolusiob: bolusiob
    };
}

function calcTempTreatments() {
    var tempHistory = [];
    var tempBoluses = [];
    var now = new Date();
    var timeZone = now.toString().match(/([-\+][0-9]+)\s/)[1]
    for (var i=0; i < pumpHistory.length; i++) {
        var current = pumpHistory[i];
        //if(pumpHistory[i].date < time) {
            if (pumpHistory[i]._type == "Bolus") {
                //console.log(pumpHistory[i]);
                var temp = {};
                temp.timestamp = current.timestamp;
                //temp.started_at = new Date(current.date);
                temp.started_at = new Date(current.timestamp + timeZone);
                //temp.date = current.date
                temp.date = temp.started_at.getTime();
                temp.insulin = current.amount
                tempBoluses.push(temp);
            } else if (pumpHistory[i]._type == "TempBasal") {
                if (current.temp == 'percent') {
                    continue;
                }
                var rate = pumpHistory[i].rate;
                var date = pumpHistory[i].date;
                if (i>0 && pumpHistory[i-1].date == date && pumpHistory[i-1]._type == "TempBasalDuration") {
                    var duration = pumpHistory[i-1]['duration (min)'];
                } else if (i+1<pumpHistory.length && pumpHistory[i+1].date == date && pumpHistory[i+1]._type == "TempBasalDuration") {
                    var duration = pumpHistory[i+1]['duration (min)'];
                } else { console.log("No duration found for "+rate+" U/hr basal"+date); }
                var temp = {};
                temp.rate = rate;
                //temp.date = date;
                temp.timestamp = current.timestamp;
                //temp.started_at = new Date(temp.date);
                temp.started_at = new Date(temp.timestamp + timeZone);
                temp.date = temp.started_at.getTime();
                temp.duration = duration;
                tempHistory.push(temp);
            }
        //}
    };
    for (var i=0; i+1 < tempHistory.length; i++) {
        if (tempHistory[i].date + tempHistory[i].duration*60*1000 > tempHistory[i+1].date) {
            tempHistory[i].duration = (tempHistory[i+1].date - tempHistory[i].date)/60/1000;
        }
    }
    var tempBolusSize;
    var now = new Date();
    var timeZone = now.toString().match(/([-\+][0-9]+)\s/)[1]
    for (var i=0; i < tempHistory.length; i++) {
        if (tempHistory[i].duration > 0) {
            var netBasalRate = tempHistory[i].rate-profile_data.current_basal;
            if (netBasalRate < 0) { tempBolusSize = -0.05; }
            else { tempBolusSize = 0.05; }
            var netBasalAmount = Math.round(netBasalRate*tempHistory[i].duration*10/6)/100
            var tempBolusCount = Math.round(netBasalAmount / tempBolusSize);
            var tempBolusSpacing = tempHistory[i].duration / tempBolusCount;
            for (var j=0; j < tempBolusCount; j++) {
                var tempBolus = {};
                tempBolus.insulin = tempBolusSize;
                tempBolus.date = tempHistory[i].date + j * tempBolusSpacing*60*1000;
                tempBolus.created_at = new Date(tempBolus.date);
                tempBoluses.push(tempBolus);
            }
        }
    }
    return [ ].concat(tempBoluses).concat(tempHistory);
    return {
        tempBoluses: tempBoluses,
        tempHistory: tempHistory
    };

}

if (!module.parent) {
    var iob_input = process.argv.slice(2, 3).pop()
    var profile_input = process.argv.slice(3, 4).pop()
    var clock_input = process.argv.slice(4, 5).pop()
  if (!iob_input || !profile_input) {
    console.log('usage: ', process.argv.slice(0, 2), '<pumphistory.json> <profile.json> <clock.json>');
    process.exit(1);
  }
    var cwd = process.cwd()
    var all_data = require(cwd + '/' + iob_input);
    var profile_data = require(cwd + '/' + profile_input);
    var clock_data = require(cwd + '/' + clock_input);
    var pumpHistory = all_data;
  pumpHistory.reverse( );
 

  var all_treatments =  calcTempTreatments( );
  //console.log(all_treatments);
  var treatments = all_treatments; // .tempBoluses.concat(all_treatments.tempHistory);
  treatments.sort(function (a, b) { return a.date > b.date });
  //var lastTimestamp = new Date(treatments[treatments.length -1].date + 1000 * 60);
  //console.log(clock_data);
  var now = new Date();
  var timeZone = now.toString().match(/([-\+][0-9]+)\s/)[1]
  var clock_iso = clock_data + timeZone;
  var clock = new Date(clock_iso);
  //console.log(clock);
  var iob = iobTotal(treatments, clock);
  //var iobs = iobTotal(treatments, lastTimestamp);
  // console.log(iobs);
  console.log(JSON.stringify(iob));
}

