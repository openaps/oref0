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
        , avgdelta: Math.round( avg * 1000 ) / 1000
    };
};

module.exports = getLastGlucose;
