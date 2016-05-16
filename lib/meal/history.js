
var tz = require('timezone');

function findMealInputs (inputs) {
    var pumpHistory = inputs.history;
    var carbHistory = inputs.carbs;
    var profile_data = inputs.profile;
    var mealInputs = [];
    for (var i=0; i < carbHistory.length; i++) {
        var current = carbHistory[i];
        if (current.carbs && current.created_at) {
            var temp = {};
            temp.timestamp = current.created_at;
            temp.carbs = current.carbs;
            mealInputs.push(temp);
        }
    }
    for (var i=0; i < pumpHistory.length; i++) {
        var current = pumpHistory[i];
        if (pumpHistory[i]._type == "Bolus") {
            //console.log(pumpHistory[i]);
            var temp = {};
            temp.timestamp = current.timestamp;
            temp.bolus = current.amount;
            mealInputs.push(temp);
        }
        if (pumpHistory[i]._type == "BolusWizard") {
            //console.log(pumpHistory[i]);
            var temp = {};
            temp.timestamp = current.timestamp;
            temp.carbs = current.carb_input;
            mealInputs.push(temp);
        }
    }
    return mealInputs;
}
exports = module.exports = findMealInputs;
