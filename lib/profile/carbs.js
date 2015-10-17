
var getTime = require('../medtronic-clock');

function carbRatioLookup (inputs) {
    var now = new Date();
    var carbratio_data = inputs.carbs;
    //carbratio_data.schedule.sort(function (a, b) { return a.offset > b.offset });
    var carbRatio = carbratio_data.schedule[carbratio_data.schedule.length - 1]
    
    for (var i = 0; i < carbratio_data.schedule.length - 1; i++) {
        if ((now >= getTime(carbratio_data.schedule[i].offset)) && (now < getTime(carbratio_data.schedule[i + 1].offset))) {
            carbRatio = carbratio_data.schedule[i];
            break;
        }
    }
    return carbRatio.ratio;
    profile.carbratio = carbRatio.ratio;
}

carbRatioLookup.carbRatioLookup = carbRatioLookup;
exports = module.exports = carbRatioLookup;
