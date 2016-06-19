
var tz = require('timezone');

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
            mealInputs.push(temp);
        }
    }
    for (var i=0; i < pumpHistory.length; i++) {
        var current = pumpHistory[i];
        if (pumpHistory[i]._type == "Bolus" && pumpHistory[i].timestamp) {
            //console.log(pumpHistory[i]);
            var temp = {};
            temp.timestamp = current.timestamp;
            temp.bolus = current.amount;
            mealInputs.push(temp);
        }
        if (pumpHistory[i]._type == "BolusWizard" && pumpHistory[i].timestamp) {
            //console.log(pumpHistory[i]);
            var temp = {};
            temp.timestamp = current.timestamp;
            temp.carbs = current.carb_input;
            
            // don't enter the treatment if there's another treatment with the same exact timestamp
            // to prevent duped carb entries from multiple sources
            
            var dupeFound = false;
            
            for (var j=0; j < mealInputs.length; j++) {
				var element = mealInputs[j];
				if (element.timestamp == current.timestamp && element.carbs) dupeFound = true;
			}
        
            if (!dupeFound) {
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