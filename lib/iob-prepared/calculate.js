var tz = require('timezone');

function iobCalc(treatment, time, dia) {
    var activityEndMinutes = (dia / 3.0) * 180 ;
    var x_peak = 75 / 180;


    if (typeof time === 'undefined') {
        time = new Date();
    }

    var results = {};

    var iobContrib = 0;
    var activityContrib = 0;

    var treatmentEndTime = new Date(tz(treatment.end_at));
    var x_end = (time-treatmentEndTime) / 1000 / 60 / activityEndMinutes;

    if (treatment.unit == "U") {
      // if x is negative iobContrib must be zero
      iobContrib = (x_end &lt; 0) ? 0 : -treatment.amount * f1(x_end);
      activityContrib = treatment.amount * f0(x_end);
    }
    else if (treatment.unit == 'U/hour') {
        var treatmentStartTime = new Date(tz(treatment.start_at));
        var x_start = (time-treatmentStartTime) / 1000 / 60 / activityEndMinutes;
        iobContrib = dia * treatment.amount * (f2(x_end) - f2(x_start));
        activityContrib = dia * treatment.amount * (f1(x_start) - f1(x_end));
    }

    results = {
        iobContrib: iobContrib,
        activityContrib: activityContrib
    };
    return results;

  // this function is the insulin activity curve for 1 U of insulin, normalized to a dia of 1
  // piecewise linear with a peak at x_peak, zero for x &lt;= 0 and x &gt;= 1
  function f0(x) {
    var transformedVars = transformX(x);
    var x1 = transformedVars.x1;
    var x2 = transformedVars.x2;
    var y = 2 * (x1/x_peak + x2/(1 - x_peak) - 1);
    return y;
  }

  // this function is the insulin appearance curve, normalized to a dia of 1
  // f1 is the integral of f0
  // f1 = -1 at x &lt;= 0, zero for x &gt;= 1
  function f1(x) {
    var transformedVars = transformX(x);
    var x1 = transformedVars.x1;
    var x2 = transformedVars.x2;
    var y = Math.pow(x1,2)/x_peak - Math.pow(x2,2)/(1 - x_peak) - x_peak;
    return y;
  }

  // this function is the integral of the iob curve f1, normalized to a dia of 1
  // f2 = 0 at x = 1
  function f2(x) {
    var transformedVars = transformX(x);
    var x1 = transformedVars.x1;
    var x2 = transformedVars.x2;
    var y = (1/3) * (Math.pow(x1,3)/x_peak + Math.pow(x2,3)/(1 - x_peak) - Math.pow(x_peak,2)) - x1 + x_peak;
    return y;
  }

  function transformX(x) {
    // limit x to [0, 1]
    x = Math.max(x, 0);
    x = Math.min(x, 1);

    // transformed variables
    var x1 = Math.min(x, x_peak)
    var x2 = Math.min(1-x, 1-x_peak)

    return {
      x1: x1,
      x2: x2
    }
  }
}
exports = module.exports = iobCalc;
