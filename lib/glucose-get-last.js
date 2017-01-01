var getLastGlucose = function (data) {
    data = data.map(function prepGlucose (obj) {
        //Support the NS sgv field to avoid having to convert in a custom way
        obj.glucose = obj.glucose || obj.sgv;
        return obj;
    });

    var now = data[0];
    var now_date = now.date || Date.parse(now.display_time) || Date.parse(then.dateString);
    var change;
    var last_deltas = [];
    var short_deltas = [];
    var long_deltas = [];

    for (i=1; i < data.length; i++) {
        if (typeof data[i] !== 'undefined' && data[i].glucose > 38) {
            var then = data[i];
            var then_date = then.date || Date.parse(then.display_time) || Date.parse(then.dateString);
            var avgdelta = 0;
            var minutesago;
            if (typeof then_date !== 'undefined' && typeof now_date !== 'undefined') {
                minutesago = Math.round( (now_date - then_date) / (1000 * 60) );
                // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
                change = now.glucose - then.glucose;
                avgdelta = change/minutesago * 5;
            } else { console.error("Error: date field not found: cannot calculate avgdelta"); }
            // use the average of all data points in the last 2.5m for all further "now" calculations
            if (0 < minutesago && minutesago < 2.5) {
                now.glucose = ( now.glucose + then.glucose ) / 2;
                now_date = ( now_date + then_date ) / 2;
            // short_deltas are calculated from everything ~5-15 minutes ago
            } else if (2.5 < minutesago && minutesago < 17.5) {
                //console.error(minutesago, avgdelta);
                short_deltas.push(avgdelta);
                // last_deltas are calculated from everything ~5 minutes ago
                if (2.5 < minutesago && minutesago < 7.5) {
                    last_deltas.push(avgdelta);
                }
            // long_deltas are calculated from everything ~20-40 minutes ago
            } else if (17.5 < minutesago && minutesago < 42.5) {
                long_deltas.push(avgdelta);
            }
        }
    }
    var last_delta = 0;
    var short_avgdelta = 0;
    var long_avgdelta = 0;
    if (last_deltas.length > 0) {
        last_delta = last_deltas.reduce(function(a, b) { return a + b; }) / last_deltas.length;
    }
    if (short_deltas.length > 0) {
        short_avgdelta = short_deltas.reduce(function(a, b) { return a + b; }) / short_deltas.length;
    }
    if (long_deltas.length > 0) {
        long_avgdelta = long_deltas.reduce(function(a, b) { return a + b; }) / long_deltas.length;
    }

    return {
        delta: Math.round( last_delta * 100 ) / 100
        , glucose: Math.round( now.glucose * 100 ) / 100
        , short_avgdelta: Math.round( short_avgdelta * 100 ) / 100
        , long_avgdelta: Math.round( long_avgdelta * 100 ) / 100
    };
};

module.exports = getLastGlucose;
