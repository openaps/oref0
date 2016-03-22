var setTempBasal = function (rate, duration, profile, rT, currenttemp) {
    maxSafeBasal = Math.min(profile.max_basal, 3 * profile.max_daily_basal, 4 * profile.current_basal);
    
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

    rT.duration = duration;
    rT.rate = Math.round((Math.round(rate / 0.05) * 0.05)*100)/100;
    return rT;
};

module.exports = setTempBasal;
