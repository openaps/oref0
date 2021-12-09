function getDateFromEntry(entry) {
  return entry.date || Date.parse(entry.display_time) || Date.parse(entry.dateString);
}

var getLastGlucose = function (data) {
    data = data.filter(function(obj) {
      return obj.glucose || obj.sgv;
    }).map(function prepGlucose (obj) {
        //Support the NS sgv field to avoid having to convert in a custom way
        obj.glucose = obj.glucose || obj.sgv;
        if ( obj.glucose !== null ) {
            return obj;
        }
    });

    var now = data[0];
    var now_date = getDateFromEntry(now);
    var change;
    var last_deltas = [];
    var short_deltas = [];
    var long_deltas = [];
    var last_cal = 0;

    //console.error(now.glucose);
    for (var i=1; i < data.length; i++) {
        // if we come across a cal record, don't process any older SGVs
        if (typeof data[i] !== 'undefined' && data[i].type === "cal") {
            last_cal = i;
            break;
        }
        // only use data from the same device as the most recent BG data point
        if (typeof data[i] !== 'undefined' && data[i].glucose > 38 && data[i].device === now.device) {
            var then = data[i];
            var then_date = getDateFromEntry(then);
            var avgdelta = 0;
            var minutesago;
            if (typeof then_date !== 'undefined' && typeof now_date !== 'undefined') {
                minutesago = Math.round( (now_date - then_date) / (1000 * 60) );
                // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
                change = now.glucose - then.glucose;
                avgdelta = change/minutesago * 5;
            } else { console.error("Error: date field not found: cannot calculate avgdelta"); }
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
            }
        }
    }
    var last_delta = 0;
    var short_avgdelta = 0;
    var long_avgdelta = 0;

    // mod 7: append 2 variables for 5% range
    var autoISF_duration = 0;
    var autoISF_average = 0;
    // mod 8: append 3 variables for deltas based on regression analysis
    var slope05 = 0;
    var slope15 = 0;
    var slope40 = 0;
    // mod 14f: append results from best fitting parabola
    var dura_p = 0;
    var delta_pl = 0;
    var delta_pn = 0;
    var r_squ = 0;
    var bg_acceleration = 0;
    var pp_debug = "; debug:";
    var log = { "Glucose: " + DecimalFormatter.to0Decimal(glucose) + " mg/dl " +
                "Noise: " + DecimalFormatter.to0Decimal(noise) + " " +
                "Delta: " + DecimalFormatter.to0Decimal(delta) + " mg/dl " +
                "Short avg. delta: " + " " + DecimalFormatter.to2Decimal(short_avgdelta) + " mg/dl " +
                "Long avg. delta: " + DecimalFormatter.to2Decimal(long_avgdelta) + " mg/dl " +
                "Range length: " + DecimalFormatter.to0Decimal(autoISF_duration) + " min " +
                "Range average: " + DecimalFormatter.to2Decimal(autoISF_average) + " mg/dl; " +
                "5 min fit delta: " + DecimalFormatter.to2Decimal(slope05) + " mg/dl; " +
                "15 min fit delta: " + DecimalFormatter.to2Decimal(slope15) + " mg/dl; " +
                "40 min fit delta: " + DecimalFormatter.to2Decimal(slope40) + " mg/dl; " +
                "parabola length: " + DecimalFormatter.to2Decimal(dura_p) + " min; " +
                "parabola last delta: " + DecimalFormatter.to2Decimal(delta_pl) + " mg/dl; " +
                "parabola next delta: " + DecimalFormatter.to2Decimal(delta_pn) + " mg/dl; " +
                "bg_acceleration: " + DecimalFormatter.to2Decimal(bg_acceleration) + " mg/dl/(25m^2); " +
                "fit correlation: " + r_squ + pp_debug;
            }



    if (last_deltas.length > 0) {
        last_delta = last_deltas.reduce(function(a, b) { return a + b; }) / last_deltas.length;
    }
    if (short_deltas.length > 0) {
        short_avgdelta = short_deltas.reduce(function(a, b) { return a + b; }) / short_deltas.length;
    }
    if (long_deltas.length > 0) {
        long_avgdelta = long_deltas.reduce(function(a, b) { return a + b; }) / long_deltas.length;
    }
    var bw = 0.05;
    var sumBG = now.glucose;
    var oldavg = now.glucose;
    var minutesdur = 0;
    for (var i = 1; i < data.length; i++) {
        var then = data[i];
        var then_date = getDateFromEntry(then);
        //  GZ mod 7c: stop the series if there was a CGM gap greater than 13 minutes, i.e. 2 regular readings
        if (Math.round((now_date - then_date) / (1000 * 60)) - minutesdur > 13) {
            break;
            }
            if (then.glucose > oldavg*(1-bw) && then.glucose < oldavg*(1+bw)) {
            sumBG += then.glucose;
            oldavg = sumBG / (i+1);
            minutesdur = Math.round((now_date - then_date) / (1000 * 60));
            } else {
            break;
        }
    }

            autoISF_average = oldavg;
            autoISF_duration = minutesdur;

    return {
        delta: Math.round( last_delta * 100 ) / 100
        , glucose: Math.round( now.glucose * 100 ) / 100
        , noise: Math.round(now.noise)
        , short_avgdelta: Math.round( short_avgdelta * 100 ) / 100
        , long_avgdelta: Math.round( long_avgdelta * 100 ) / 100
        , autoISF_average: Math.round( autoISF_average * 100) / 100
        , autoISF_duration: Math.round(autoISF_duration * 100) / 100
        , date: now_date
        , last_cal: last_cal
        , device: now.device
    };
};

module.exports = getLastGlucose;
