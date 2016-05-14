var setTempBasal = function (rate, duration, profile, rT, currenttemp) {
    var maxSafeBasal = Math.min(profile.max_basal, 3 * profile.max_daily_basal, 4 * profile.current_basal);
    
    if (rate < 0) { 
        rate = 0; 
    } // if >30m @ 0 required, zero temp will be extended to 30m instead
    else if (rate > maxSafeBasal) { 
        rate = maxSafeBasal; 
    }
    
    if (typeof(currenttemp) !== 'undefined' && typeof(currenttemp.duration) !== 'undefined' && typeof(currenttemp.rate) !== 'undefined' && currenttemp.duration > 20 && rate < currenttemp.rate + 0.1 && rate > currenttemp.rate - 0.1) {
        rT.reason += ", but "+currenttemp.duration+"m left and " + currenttemp.rate + " ~ req " + rate + "U/hr: no action required";
        return rT;
    }

    var suggestedRate = Math.round((Math.round(rate / 0.05) * 0.05)*100)/100;
    if (suggestedRate === profile.current_basal) {
      if (profile.skip_neutral_temps) {
        if (typeof(currenttemp) !== 'undefined' && typeof(currenttemp.duration) !== 'undefined' && currenttemp.duration > 0) {
          reason(rT, 'Suggested rate is same as profile rate, a temp basal is active, canceling current temp');
          rT.duration = 0;
          rT.rate = 0;
          return rT;
        } else {
          reason(rT, 'Suggested rate is same as profile rate, no temp basal is active, doing nothing');
          return rT;
        }
      } else {
        reason(rT, 'Setting neutral temp basal of ' + profile.current_basal + 'U/hr');
        rT.duration = duration;
        rT.rate = suggestedRate;
        return rT;
      }
    } else {
      rT.duration = duration;
      rT.rate = suggestedRate;
      return rT;
    }
};

function reason(rT, msg) {
  rT.reason = (rT.reason ? rT.reason + '. ' : '') + msg;
  console.error(msg);
}

module.exports = setTempBasal;
