const moment = require('moment');
const _ = require('lodash');
const stats = require('./glucose-stats');

module.exports = {};
const calcStatsExports = module.exports;

calcStatsExports.updateGlucoseStats = (options) => {
  var hist = _.map(_.sortBy(options.glucose_hist, 'dateString'), function readDate(value) {
      value.readDateMills = moment(value.dateString).valueOf();
      return value;
    });

  if (hist && hist.length > 0) {
    var noise_val = stats.calcSensorNoise(null, hist, null, null);

    var ns_noise_val = stats.calcNSNoise(noise_val, hist);

    if ('noise' in options.glucose_hist[0]) {
      console.error("Glucose noise CGM reported level: ", options.glucose_hist[0].noise);
      ns_noise_val = Math.max(ns_noise_val, options.glucose_hist[0].noise);
    }

    console.error("Glucose noise calculated: ", noise_val, " setting noise level to ", ns_noise_val);

    options.glucose_hist[0].noise = ns_noise_val;
  }

  return options.glucose_hist;
};
