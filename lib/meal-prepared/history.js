
var tz = require('timezone');

function arrayHasElementWithSameTimestampAndProperty(array,t,propname) {
	for (var j=0; j < array.length; j++) {
		var element = array[j];
		if (element.timestamp == t && element[propname] != undefined) return true;
	}
    return false;
}

function findMealInputs (inputs) {
    var pumpHistory = inputs.history;
    var carbHistory = inputs.carbs;
    var profile_data = inputs.profile;
    var mealInputs = [];
    var duplicates = 0;

    for (var i=0; i < carbHistory.length; i++) {
        var current = carbHistory[i];
        if (current.carbs && current.created_at) {
            var temp = {};
            temp.timestamp = current.created_at;
            temp.carbs = current.carbs;

			if (!arrayHasElementWithSameTimestampAndProperty(mealInputs,current.created_at,"carbs")) {
            	mealInputs.push(temp);
            } else {
            	duplicates += 1;
            }
        }
    }
    for (var i=0; i < pumpHistory.length; i++) {
        var current = pumpHistory[i];
        if (pumpHistory[i].type == "Bolus" && pumpHistory[i].start_at && pumpHistory[i].unit == "U") {
            //console.log(pumpHistory[i]);
            var temp = {};
            temp.timestamp = current.start_at;
            temp.bolus = current.amount;

            if (!arrayHasElementWithSameTimestampAndProperty(mealInputs,current.timestamp,"bolus")) {
            	mealInputs.push(temp);
            } else {
            	duplicates += 1;
            }
        }
        if (pumpHistory[i].type == "Meal" && pumpHistory[i].start_at) {
            //console.log(pumpHistory[i]);
            var temp = {};
            temp.timestamp = current.start_at;
            temp.carbs = current.amount;

            // don't enter the treatment if there's another treatment with the same exact timestamp
            // to prevent duped carb entries from multiple sources
    		if (!arrayHasElementWithSameTimestampAndProperty(mealInputs,current.timestamp,"carbs")) {
            	mealInputs.push(temp);
            } else {
            	duplicates += 1;
            }
        }
    }

    if (duplicates > 0) console.error("Removed duplicate bolus/carb entries:" + duplicates);

    return mealInputs;
}

exports = module.exports = findMealInputs;
