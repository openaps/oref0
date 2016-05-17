
var getTime = require('../medtronic-clock');

function carbRatioLookup (inputs) {
    var now = new Date();
    var carbratio_data = inputs.carbratio;
    if (typeof(carbratio_data) != "undefined" && typeof(carbratio_data.schedule) != "undefined") {
        var carbRatio;
        if ((carbratio_data.units == "grams") || (carbratio_data.units == "exchanges")) {
            //carbratio_data.schedule.sort(function (a, b) { return a.offset > b.offset });
            carbRatio = carbratio_data.schedule[carbratio_data.schedule.length - 1];

            for (var i = 0; i < carbratio_data.schedule.length - 1; i++) {
                if ((now >= getTime(carbratio_data.schedule[i].offset)) && (now < getTime(carbratio_data.schedule[i + 1].offset))) {
                    carbRatio = carbratio_data.schedule[i];
                    break;
                }
            }
            if (carbratio_data.units == "exchanges") {
                carbRatio.ratio = 12 / carbRatio.ratio
            }
        return carbRatio.ratio;
        } else {
            console.error("Error: Unsupported carb_ratio units " + carbratio_data.units);
            return;
        }
    //return carbRatio.ratio;
    //profile.carbratio = carbRatio.ratio;
    } else { return; }
}

carbRatioLookup.carbRatioLookup = carbRatioLookup;
exports = module.exports = carbRatioLookup;
