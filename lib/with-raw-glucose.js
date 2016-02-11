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

module.exports = function withRawGlucose (entry, cal, maxRaw) {
  maxRaw = maxRaw || 150;

  var glucose = entry.glucose || entry.sgv || 0;

  entry.unfiltered = parseInt(entry.unfiltered) || 0;
  entry.filtered = parseInt(entry.filtered) || 0;

  cal = cleanCal(cal);

  if (cal.valid && (cal.filtered === 0 || glucose < 40)) {
    entry.raw = Math.round(cal.scale * (entry.unfiltered - cal.intercept) / cal.slope);
  } else if (cal.valid) {
    var ratio = cal.scale * (entry.filtered - cal.intercept) / cal.slope / glucose;
    entry.raw = Math.round(cal.scale * (entry.unfiltered - cal.intercept) / cal.slope / ratio);
  }

  if (entry.raw && (entry.glucose < 40 || !entry.glucose) && entry.raw < maxRaw) {
    entry.glucose = entry.raw;
    entry.fromRaw = true;
  }

  return entry;
};