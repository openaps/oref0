'use strict';

function cleanCal (cal) {
  var clean = {
    scale: parseFloat(cal.scale) || 0
    , intercept: parseFloat(cal.intercept) || 0
    , slope: parseFloat(cal.slope) || 0
  };

  clean.valid = ! (clean.slope === 0 || clean.unfiltered === 0 || clean.scale === 0);

  return clean;
}

module.exports = function withRawGlucose (entry, cals, max_raw, raw_safety_multiplier) {
  var maxRaw = maxRaw || 150;
  var raw_safety_multiplier = raw_safety_multiplier || 0.75;

  var egv = entry.glucose || entry.sgv || 0;

  entry.unfiltered = parseInt(entry.unfiltered) || 0;
  entry.filtered = parseInt(entry.filtered) || 0;

  //TODO: add time check, but how recent should it be?
  //TODO: currently assuming the first is the best (and that there is probably just 1 cal)
  var cal = cals && cals.length > 0 && cleanCal(cals[0]);

  if (cal && cal.valid) {
    if (cal.filtered === 0 || egv < 40) {
      entry.raw = Math.round(cal.scale * (entry.unfiltered - cal.intercept) / cal.slope);
    } else {
      var ratio = cal.scale * (entry.filtered - cal.intercept) / cal.slope / egv;
      entry.raw = Math.round(cal.scale * (entry.unfiltered - cal.intercept) / cal.slope / ratio);
    }

    var adjustedRaw = entry.raw * raw_safety_multiplier;
    if (adjustedRaw && egv < 40 && adjustedRaw < maxRaw) {
      entry.glucose = adjustedRaw;
      entry.fromRaw = true;
    }
  }

  return entry;
};
