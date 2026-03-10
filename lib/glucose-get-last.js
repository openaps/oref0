
function getDateFromEntry(entry) {
  return entry.date || Date.parse(entry.display_time) || Date.parse(entry.dateString);
}

var getLastGlucose = function (data) {
    var now = undefined;
    var now_date = undefined;
    var change;
    var last_deltas = [];
    var short_deltas = [];
    var long_deltas = [];
    var last_cal = 0;

    //console.error(now.glucose);
    for (var i=0; i < data.length; i++) {
        // if we come across a cal record, don't process any older SGVs
        var item = data[i];
        item.glucose = item.glucose || item.sgv;
        if (!item.glucose) {
            continue;
        }
        if (typeof now === 'undefined') {
            now = item;
            now_date = getDateFromEntry(item);
            continue;
        }
        if (typeof now === 'undefined') {
            continue;
        }
        if (item.type === "cal") {
            last_cal = i;
            break;
        }
        
        // only use data from the same device as the most recent BG data point
        if (item.glucose > 38 && item.device === now.device) {
            var then = item;
            var then_date = getDateFromEntry(then);
            var avgdelta = 0;
            var minutesago;
            if (typeof then_date !== 'undefined' && typeof now_date !== 'undefined') {
                minutesago = Math.round( (now_date - then_date) / (1000 * 60) );
                // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
                change = now.glucose - then.glucose;
                avgdelta = change/minutesago * 5;
            } else {
                console.error("Error: date field not found: cannot calculate avgdelta");
                continue;
            }
            //if (i < 5) {
                //console.error(then.glucose, minutesago, avgdelta);
            //}
            // use the average of all data points in the last 2.5m for all further "now" calculations
            if (-2 < minutesago && minutesago < 2.5) {
                now.glucose = ( now.glucose + then.glucose ) / 2;
                now_date = ( now_date + then_date ) / 2;
                //console.error(then.glucose, now.glucose);
            // short_deltas are calculated from everything ~5-15 minutes ago
            } else if (2.5 < minutesago && minutesago < 17.5) {
                //console.error(minutesago, avgdelta);
                short_deltas.push(avgdelta);
                // last_deltas are calculated from everything ~5 minutes ago
                if (2.5 < minutesago && minutesago < 7.5) {
                    last_deltas.push(avgdelta);
                }
                //console.error(then.glucose, minutesago, avgdelta, last_deltas, short_deltas);
            // long_deltas are calculated from everything ~20-40 minutes ago
            } else if (17.5 < minutesago && minutesago < 42.5) {
                long_deltas.push(avgdelta);
            } else if (minutesago > 42.5) {
                break;
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
        , noise: Math.round(now.noise)
        , short_avgdelta: Math.round( short_avgdelta * 100 ) / 100
        , long_avgdelta: Math.round( long_avgdelta * 100 ) / 100
        , date: now_date
        , last_cal: last_cal
        , device: now.device
    };
};

module.exports = getLastGlucose;
