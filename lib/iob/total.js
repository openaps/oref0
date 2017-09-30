function iobTotal(opts, time) {

    var now = time.getTime();
    var iobCalc = opts.calculate;
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    var iob = 0;
    //var bolussnooze = 0;
    var activity = 0;
    if (!treatments) return {};
    //if (typeof time === 'undefined') {
        //var time = new Date();
    //}

    treatments.forEach(function(treatment) {
        if(treatment.date <= time.getTime( )) {
            var dia = profile_data.dia;
            // force minimum DIA of 3h
            if (dia < 3) {
                console.error("Warning; adjusting DIA from",dia,"to minimum of 3 hours");
                dia = 3;
            }
            var dia_ago = now - profile_data.dia*60*60*1000;
            // tIOB = total IOB
            var tIOB = iobCalc(treatment, time, dia, profile_data);
            if (tIOB && tIOB.iobContrib) iob += tIOB.iobContrib;
            if (tIOB && tIOB.activityContrib) activity += tIOB.activityContrib;
            // for purposes of categorizing boluses as SMBs to add to basalIOB, use max_daily_basal
            if (typeof profile_data.maxSMBBasalMinutes == 'undefined' ) {
                var maxSMB = profile_data.max_daily_basal * 30 / 60;
                //console.error("profile.maxSMBBasalMinutes undefined: defaulting to 30m");
            } else {
                var maxSMB = profile_data.max_daily_basal * 60 / profile_data.maxSMBBasalMinutes;
            }
            // keep track of bolus IOB separately for snoozes, but decay it twice as fast
            // only snooze for boluses that deliver more than maxSMBBasalMinutes m worth of basal (excludes SMBs)
            if (treatment.insulin > maxSMB && treatment.started_at) {
                //default bolussnooze_dia_divisor is 2, for 2x speed bolus snooze
                // bIOB = bolus IOB
                if (tIOB.biobContrib !== undefined) {
                    //bolussnooze += tIOB.biobContrib;
                } else {
                    //var bIOB = iobCalc(treatment, time, dia / profile_data.bolussnooze_dia_divisor, profile_data);
                    //console.log(treatment);
                    //console.log(bIOB);
                    //if (bIOB && bIOB.iobContrib) bolussnooze += bIOB.iobContrib;
                }
            } else {
                // aIOB = basal IOB
                var aIOB = tIOB; // iobCalc(treatment, time, dia, profile_data);
            }
        }
    });

    var rval = {
        iob: Math.round(iob * 1000) / 1000,
        activity: Math.round(activity * 10000) / 10000,
        //bolussnooze: Math.round(bolussnooze * 1000) / 1000,
        time: time
    };

    return rval;
}

exports = module.exports = iobTotal;
