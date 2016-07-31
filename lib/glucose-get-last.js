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
    var avg = 0;

    //console.error(data);
    //TODO: calculate average using system_time instead of assuming 1 data point every 5m
    if (typeof data[6] !== 'undefined' && data[6].glucose > 30) {
        then = data[6];
    } else if (typeof data[5] !== 'undefined' && data[5].glucose > 30) {
        then = data[5];
    } else if (typeof data[4] !== 'undefined' && data[4].glucose > 30) {
        then = data[4];
    } else if (typeof data[3] !== 'undefined' && data[3].glucose > 30) {
        then = data[3];
    } else if (typeof data[2] !== 'undefined' && data[2].glucose > 30) {
        then = data[2];
    } else if (typeof data[1] !== 'undefined' && data[1].glucose > 30) {
        then = data[1];
        secondlast = data[1];
    } else {
        then = data[0];
    }
    change = now.glucose - then.glucose;

    var then_date = then.date || Date.parse(then.display_time);
    var now_date = now.date || Date.parse(now.display_time);

    if (typeof then_date !== 'undefined' && typeof now_date !== 'undefined') {
        minutes = Math.round( (now_date - then_date) / (1000 * 60) );
        console.error("Avgdelta lookback", minutes, "minutes");
        // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
        avg = change/minutes * 5;
    } else { console.error("Error: date field not found: cannot calculate avgdelta"); }

    if (typeof data[2] !== 'undefined' && data[2].glucose > 30) {
        secondtolast = data[2];
    } else if (typeof data[1] !== 'undefined' && data[1].glucose > 30) {
        secondtolast = data[1];
    } else {
        secondtolast = data[0];
    }

		var older_date = secondtolast.date || Date.parse(secondtolast.display_time);
    twochange = now.glucose - secondtolast.glucose;
    if (typeof older_date !== 'undefined' && typeof now_date !== 'undefined') {
        minutes = Math.round( (now_date - older_date) / (1000 * 60) );
        console.error("Two data point lookback", minutes, "minutes");
        // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
        twoavg = twochange/minutes * 5;
    } else { console.error("Error: date field not found: cannot calculate twodelta"); }

    return {
        delta: now.glucose - last.glucose
        , glucose: now.glucose
        , avgdelta: Math.round( avg * 1000 ) / 1000
        , twodelta: Math.round( twoavg * 1000 ) / 1000
    };
};

module.exports = getLastGlucose;
