
function iobTotal(opts, time) {
    var iobCalc = opts.calculate;
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    var iob = 0;
    var bolussnooze = 0;
    var basaliob = 0;
    var activity = 0;
    if (!treatments) return {};
    //if (typeof time === 'undefined') {
        //var time = new Date();
    //}

    treatments.forEach(function(treatment) {
        if(treatment.date <= time.getTime( )) {
            var dia = profile_data.dia;
            var tIOB = iobCalc(treatment, time, dia);
            if (tIOB && tIOB.iobContrib) iob += tIOB.iobContrib;
            if (tIOB && tIOB.activityContrib) activity += tIOB.activityContrib;
            // keep track of bolus IOB separately for snoozes, but decay it twice as fast
            if (treatment.insulin >= 0.2 && treatment.started_at) {
                //use half the dia for double speed bolus snooze
                var bIOB = iobCalc(treatment, time, dia / 2);
                //console.log(treatment);
                //console.log(bIOB);
                if (bIOB && bIOB.iobContrib) bolussnooze += bIOB.iobContrib;
            } else {
                var aIOB = iobCalc(treatment, time, dia);
                if (aIOB && aIOB.iobContrib) basaliob += aIOB.iobContrib;
            }
        }
    });

    return {
        iob: Math.round( iob * 1000 ) / 1000,
        activity: Math.round( activity * 10000 ) / 10000,
        bolussnooze: Math.round( bolussnooze * 1000 ) / 1000,
        basaliob: Math.round( basaliob * 1000 ) / 1000,
    };
}

exports = module.exports = iobTotal;

