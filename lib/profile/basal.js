
var getTime = require('../medtronic-clock');

/* Return basal rate(U / hr) at the provided timeOfDay */
function basalLookup (schedules) {
    var basalprofile_data = schedules;
    var now = new Date();
    var basalRate = basalprofile_data[basalprofile_data.length-1].rate
    
    for (var i = 0; i < basalprofile_data.length - 1; i++) {
        if ((now >= getTime(basalprofile_data[i].minutes)) && (now < getTime(basalprofile_data[i + 1].minutes))) {
            basalRate = basalprofile_data[i].rate;
            break;
        }
    }
    return Math.round(basalRate*1000)/1000;
}


function maxDailyBasal (inputs) {
    var basalprofile_data = inputs.basals;
    basalprofile_data.sort(function (a, b) { if (a.rate < b.rate) { return 1 } if (a.rate > b.rate) { return -1; } return 0; });
    return Math.round( basalprofile_data[0].rate *1000)/1000;
}

/*Return maximum daily basal rate(U / hr) from profile.basals */

function maxBasalLookup (inputs) {
    
    return inputs.settings.maxBasal;
}


exports.maxDailyBasal = maxDailyBasal;
exports.maxBasalLookup = maxBasalLookup;
exports.basalLookup = basalLookup;
