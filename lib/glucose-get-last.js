var getLastGlucose = function (data) {
    data = data.map(function prepGlucose (obj) {
        //Support the NS sgv field to avoid having to convert in a custom way
        obj.glucose = obj.glucose || obj.sgv;
        return obj;
    });

    var now = data[0];
    var last = data[1];
    var minutes;
    var change;
    var avg;
    var isValid = false;
    
    //We will check all records for valid timestamps, we cannot make decision if:
    // - Last record is too old or is highly in the future (in this case dexcom/PI clock should be checked)
    // - there is a big time difference between at least 2 last records (in this case average calculation is useless)
    // - third record is older than 3 hours
    isValid = checkGlucoseDateValidity(data[0], new Date(), 5, 10)
    if (isValid) {
        isValid = checkGlucoseDateValidity(data[1], new Date(data[0].date), -4, 16);
        if (isValid) { 
            isValid = checkGlucoseDateValidity(data[2], new Date(data[1].date), -4, 60*3);
        }
    }
    
    if (!isValid) {
        console.error("Glucose data is not valid");
        return {
            isValid: isValid
        };
    }

    //TODO: calculate average using system_time instead of assuming 1 data point every 5m
    if (typeof data[3] !== 'undefined' && data[3].glucose > 30) {
        minutes = 3*5;
        change = now.glucose - data[3].glucose;
    } else if (typeof data[2] !== 'undefined' && data[2].glucose > 30) {
        minutes = 2*5;
        change = now.glucose - data[2].glucose;
    } else if (typeof last !== 'undefined' && last.glucose > 30) {
        minutes = 5;
        change = now.glucose - last.glucose;
    } else { change = 0; }
    // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
    avg = change/minutes * 5;

    return {
        delta: now.glucose - last.glucose
        , glucose: now.glucose
        , avgdelta: Math.round(avg * 1000) / 1000
        , isValid: isValid
    };
};


function checkGlucoseDateValidity(glucoseRecord, baseTime, forwardMaxDifference, backwardMaxDifference) {
    var bgTime;
    if (glucoseRecord.display_time) {
        bgTime = new Date(glucoseRecord.display_time.replace('T', ' '));
        if (checkGlucoseDateIsInMinutesRange(bgTime, baseTime, forwardMaxDifference, backwardDeviatio)) {
            glucoseRecord.date = bgTime.getTime(); // We ensure that we have a valid date in .date for future use
            return true;
        }
    }
    if (glucoseRecord.dateString) {
        bgTime = new Date(glucoseRecord.dateString);
        if (checkGlucoseDateIsInMinutesRange(bgTime, baseTime, forwardMaxDifference, backwardDeviatio)) {
            glucoseRecord.date = bgTime.getTime(); // We ensure that we have a valid date in .date for future use
            return true;
        }
    }
    if (glucoseRecord.date) {
        bgTime = new Date(glucoseRecord.date);
        if (checkGlucoseDateIsInMinutesRange(bgTime, baseTime, forwardMaxDifference, backwardDeviatio))
            return true;
    }
    console.error("Cannot parse glucose date field. Please check the input file");

    return false;
		
}
function checkGlucoseDateIsInMinutesRange(bgTime, baseTime, forwardMaxDifference, backwardDeviatio) {
    //Check for Invalid Date
    if (bgTime instanceof Date && isFinite(bgTime)) {
        var minTime = baseTime - (backwardDeviatio * 60000)
        var maxTime = baseTime + (forwardMaxDifference * 60000)
        if (bgTime >= minTime && bgTime <= maxTime) { // We are in range
            return true;
        }
        else {
            console.error("Glucose reading date " + new Date(bgTime).toISOString() + " is not in required range (from " + new Date(minTime).toISOString() + " to " + new Date(maxTime).toISOString() + ")");
        }
    }
    return false;
}



module.exports = getLastGlucose;
