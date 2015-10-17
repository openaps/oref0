
function iobTotal(opts, time) {
    var iobCalc = opts.calculate;
    var treatments = opts.treatments;
    var profile_data = opts.profile;
    var iob = 0;
    var bolusiob = 0;
    var activity = 0;
    if (!treatments) return {};
    //if (typeof time === 'undefined') {
        //var time = new Date();
    //}

    treatments.forEach(function(treatment) {
        if(treatment.date < time.getTime( )) {
            var dia = profile_data.dia;
            var tIOB = iobCalc(treatment, time, dia);
            if (tIOB && tIOB.iobContrib) iob += tIOB.iobContrib;
            if (tIOB && tIOB.activityContrib) activity += tIOB.activityContrib;
            // keep track of bolus IOB separately for snoozes, but decay it three times as fast
            if (treatment.insulin >= 0.2 && treatment.started_at) {
                var bIOB = iobCalc(treatment, time, dia*2)
                //console.log(treatment);
                //console.log(bIOB);
                if (bIOB && bIOB.iobContrib) bolusiob += bIOB.iobContrib;
            }
        }
    });

    return {
        iob: iob,
        activity: activity,
        bolusiob: bolusiob
    };
}

exports = module.exports = iobTotal;

