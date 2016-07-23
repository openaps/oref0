
var getTime = require('../medtronic-clock');

function isfLookup (inputs) {
    var now = new Date();
    var isf_data = inputs.isf;
    //isf_data.sensitivities.sort(function (a, b) { return a.offset > b.offset });
    var isfSchedule = isf_data.sensitivities[isf_data.sensitivities.length - 1]
    
    if (isf_data.sensitivities[0].offset != 0 || isf_data.sensitivities[0].i != 0 || isf_data.sensitivities[0].x != 0 || isf_data.sensitivities[0].start != "00:00:00") {
        return -1;
    }
    for (var i = 0; i < isf_data.sensitivities.length - 1; i++) {
        if ((now >= getTime(isf_data.sensitivities[i].offset)) && (now < getTime(isf_data.sensitivities[i + 1].offset))) {
            isfSchedule = isf_data.sensitivities[i];
            break;
        }
    }
    return isfSchedule.sensitivity;
}

isfLookup.isfLookup = isfLookup;
exports = module.exports = isfLookup;

