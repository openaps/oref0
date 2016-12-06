function iobTotal(opts, time) {
  var now = time.getTime();
  var iobCalc = opts.calculate;
  var treatments = opts.treatments;
  var profile_data = opts.profile;
  var iob = 0;
  var bolussnooze = 0;
  var basaliob = 0;
  var activity = 0;
  if (!treatments) return {};

  treatments.forEach(function(treatment) {
    var dia = profile_data.dia;
    var tIOB = iobCalc(treatment, time, dia);
    if (tIOB && tIOB.iobContrib) iob += tIOB.iobContrib;
    if (tIOB && tIOB.activityContrib) activity += tIOB.activityContrib;
    // keep track of bolus IOB separately for snoozes, but decay it twice as fast
    if (treatment.type == "Bolus") {
      //default bolussnooze_dia_divisor is 2, for 2x speed bolus snooze
      var bIOB = iobCalc(treatment, time, dia / profile_data.bolussnooze_dia_divisor);
      //console.log(treatment);
      //console.log(bIOB);
      if (bIOB && bIOB.iobContrib) bolussnooze += bIOB.iobContrib;
    } else if (treatment.type == "TempBasal"){
      var aIOB = iobCalc(treatment, time, dia);
      if (aIOB && aIOB.iobContrib) basaliob += aIOB.iobContrib;
    }
  });

  return {
    iob: Math.round( iob * 1000 ) / 1000,
    activity: Math.round( activity * 10000 ) / 10000,
    bolussnooze: Math.round( bolussnooze * 1000 ) / 1000,
    basaliob: Math.round( basaliob * 1000 ) / 1000,
    time: time
  };
}

exports = module.exports = iobTotal;
