var setTempBasal = function (rate, duration, profile, rT, offline) {
    maxSafeBasal = Math.min(profile.max_basal, 3 * profile.max_daily_basal, 4 * profile.current_basal);
    
    if (rate < 0) { 
        rate = 0; 
    } // if >30m @ 0 required, zero temp will be extended to 30m instead
    else if (rate > maxSafeBasal) { 
        rate = maxSafeBasal; 
    }
    
    // rather than canceling temps, if Offline mode is set, always set the current basal as a 30m temp
    // so we can see on the pump that openaps is working
    if (duration == 0 && offline == 'Offline') {
        rate = profile.current_basal;
        duration  = 30;
    }

    rT.duration = duration;
    rT.rate = Math.round((Math.round(rate / 0.05) * 0.05)*100)/100;
    return rT;
};

module.exports = setTempBasal;