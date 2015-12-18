
var tz = require('timezone');

function calcTempTreatments (inputs) {
  var pumpHistory = inputs.history;
  var profile_data = inputs.profile;
    var tempHistory = [];
    var tempBoluses = [];
    var now = new Date();
    var timeZone = now.toString().match(/([-\+][0-9]+)\s/)[1];
    for (var i=0; i < pumpHistory.length; i++) {
        var current = pumpHistory[i];
        //if(pumpHistory[i].date < time) {
            if (pumpHistory[i]._type == "Bolus") {
                //console.log(pumpHistory[i]);
                var temp = {};
                temp.timestamp = current.timestamp;
                //temp.started_at = new Date(current.date);
                temp.started_at = new Date(tz(current.timestamp));
                //temp.date = current.date
                temp.date = temp.started_at.getTime();
                temp.insulin = current.amount;
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
                } else { console.error("No duration found for "+rate+" U/hr basal"+date, pumpHistory[i - 1], pumpHistory[i], pumpHistory[i + 1]); }
                var temp = {};
                temp.rate = rate;
                //temp.date = date;
                temp.timestamp = current.timestamp;
                //temp.started_at = new Date(temp.date);
                temp.started_at = new Date(tz(temp.timestamp));
                temp.date = temp.started_at.getTime();
                temp.duration = duration;
                tempHistory.push(temp);
            }
        //}
    }
    tempHistory.sort(function (a, b) { if (a.date > b.date) { return 1 } if (a.date < b.date) { return -1; } return 0; });
    for (var i=0; i+1 < tempHistory.length; i++) {
        if (tempHistory[i].date + tempHistory[i].duration*60*1000 > tempHistory[i+1].date) {
            tempHistory[i].duration = (tempHistory[i+1].date - tempHistory[i].date)/60/1000;
        }
    }
    var tempBolusSize;
    var now = new Date();
    var timeZone = now.toString().match(/([-\+][0-9]+)\s/)[1];
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
    var all_data =  [ ].concat(tempBoluses).concat(tempHistory);
    all_data.sort(function (a, b) { return a.date > b.date });
    return all_data;
}
exports = module.exports = calcTempTreatments;
