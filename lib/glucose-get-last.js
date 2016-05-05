var getLastGlucose = function (data) {

	var interpolationEngine = require('natural-spline-interpolator');


	
	//First let's check if we can parse "now" record, having no "now" record means we cannot loop at all.
	if (typeof data === 'undefined' || !checkGlucoseDateValidity(data[0]))
		return {
			reasonHint: "Glucose data parsing error",
			isFailure: true
		}
	//Then we'll check 2nd and 3rd BG readings, not critical anymore
	//so we shouldn 't just fail but we' ll generate a suggestion file without enact - suggestion
	if (!checkGlucoseDateValidity(data[1]) || !checkGlucoseDateValidity(data[2]))
		return {
			reasonHint: "Glucose data parsing error (not critical)",
			isFailure: false
			, isValid: false
			, glucose: 0 //TODO: remove these after determine-basal will process isValid
			, delta: 0
			, avgdelta: 0
		}
	
	//If last or second-last bg reading is too old - we shouldn't suggest anything
	if (!checkTimeRange(data[0].date, new Date(), 5, 10) //if bgTime is not older tat now-5min and not newer than now+10min
	|| !checkTimeRange(data[1].date, data[0].date, -4, 32)//if 2nd bgTime is not older than flast bgTime-30m and not newer than 1st bgTime -4min
	 //(last condition (not newer than) is for wrong data)
		)
	{
		return {
			isFailure: false,
			isValid: false,
			reasonHint: "Last 2 BG readings are too old"
			, glucose: 0 //TODO: remove these after determine-basal will process isValid
			, delta: 0
			, avgdelta: 0
		}
	}
	
	data = data.map(function prepGlucose(obj) {
		//Support the NS sgv field to avoid having to convert in a custom way
		obj.glucose = obj.glucose || obj.sgv;
		return obj;
	});
	
	//Number of readings to help interpolation
	var maxNumberOfReadings = 4

	var neededReadings = (data.length < maxNumberOfReadings)?data.length : maxNumberOfReadings;

	var glucoseArray = new Array(neededReadings);
	for (i = 0; i < neededReadings; i++) {
		var dataArray = new Array(2);
		dataArray[0] = minutesFromNow(data[i].date);
		dataArray[1] = data[i].glucose;
		glucoseArray[i] = dataArray;
	}
	interpolate = interpolationEngine(glucoseArray);


	
	var delta1 = interpolate(0) - interpolate(5)
	var delta2 = interpolate(5) - interpolate(10)
	//var delta3 = interpolate(10) - interpolate(15)
	
	var avgdelta = Math.round( (delta1 + delta2) / 2 * 1000) / 1000

	return {
		delta: Math.round(interpolate(0) - interpolate(5))
		, glucose: Math.round(interpolate(0))
		, avgdelta: avgdelta
		, isFailure: false
		, isValid: true

	};
};


function checkGlucoseDateValidity(glucoseRecord) {
	if (typeof glucoseRecord !== 'undefined') {
		var bgTime;
		if (glucoseRecord.display_time) {
			bgTime = new Date(glucoseRecord.display_time.replace('T', ' '));
			if (checkGlucoseDate(bgTime)) {
				glucoseRecord.date = bgTime.getTime(); // We ensure that we have a valid date in .date for future use
				glucoseRecord
				return true;
			}
		}
		if (glucoseRecord.dateString) {
			bgTime = new Date(glucoseRecord.dateString);
			if (checkGlucoseDate(bgTime)) {
				glucoseRecord.date = bgTime.getTime(); // We ensure that we have a valid date in .date for future use
				return true;
			}
		}
		if (glucoseRecord.date) {
			if (typeof (glucoseRecord.date) === 'string') 
				glucoseRecord.date.replace('T', ' ');
			bgTime = new Date(glucoseRecord.date);
			if (checkGlucoseDate(bgTime))
				return true;
		}
	}
	console.error("Cannot parse glucose date field. Please check the input file");
	
	return false;
		
}
function checkGlucoseDate(bgTime) {
	//Check for Invalid Date
	return  (bgTime instanceof Date && isFinite(bgTime))
}

function checkTimeRange(bgTime, baseTime, forwardMinutes, backwardMinutes) {
	var minTime = new Date(baseTime).getTime() - (backwardMinutes * 60000)
	var maxTime = new Date(baseTime).getTime() + (forwardMinutes * 60000)
	return (bgTime >= minTime && new Date(bgTime) <= maxTime);

}

function minutesFromNow(date) {
	var now = new Date();
	var result = (now - date) / 1000 / 60;
	return result;
}




module.exports = getLastGlucose;
