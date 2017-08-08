var _ = require('lodash');

var cache = null;
var data_ref = null;

function isfLookup(isf_data, timestamp) {

    var nowDate = timestamp;

    if (typeof(timestamp) === 'undefined') {
        nowDate = new Date();
    }

    // build cache if it doesn't exist

    if (cache == undefined || isf_data !== data_ref) {

        console.error('Building ISF cache with 30 minute resolution');
        cache = [];
        data_ref = isf_data;

        var reduced_data = _.sortBy(isf_data.sensitivities, function(o) {
            return o.offset;
        });

        for (i = 0; i < 48; i++) {

            var referenceMinutes = i * 30;
            var isfSchedule = reduced_data[reduced_data.length - 1];
            var skipper = 0;

            if (reduced_data.length > 1) {
                for (var j = skipper; j < reduced_data.length - 1; j++) {
                    var currentISF = reduced_data[j];
                    var nextISF = reduced_data[j + 1];
                    if (referenceMinutes >= currentISF.offset && referenceMinutes < nextISF.offset) {
                        isfSchedule = reduced_data[j];
                        skipper = j;
                        break;
                    }
                }
            }
            cache[i] = isfSchedule.sensitivity;
        }
    }

    var nowMinutes = nowDate.getHours() * 60 + nowDate.getMinutes();

    return cache[Math.floor(nowMinutes / 30)];

}

isfLookup.isfLookup = isfLookup;
exports = module.exports = isfLookup;