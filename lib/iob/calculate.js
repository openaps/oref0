
function iobCalc(treatment, time, dia) {
    var diaratio = dia / 3;
    var peak = 75 ;
    var end = 180 ;
    //var sens = profile_data.sens;
    if (typeof time === 'undefined') {
        var time = new Date();
    }

    if (treatment.insulin) {
        var bolusTime=new Date(treatment.date);
        var minAgo=(time-bolusTime)/1000/60 * diaratio;

        if (minAgo < 0) { 
            var iobContrib=0;
            var activityContrib=0;
        }
        else if (minAgo < peak) {
            var x = (minAgo/5 + 1);
            var iobContrib=treatment.insulin*(1-0.001852*x*x+0.001852*x);
            //var activityContrib=sens*treatment.insulin*(2/dia/60/peak)*minAgo;
            var activityContrib=treatment.insulin*(2/dia/60/peak)*minAgo;
        }
        else if (minAgo < end) {
            var x = (minAgo-peak)/5;
            var iobContrib=treatment.insulin*(0.001323*x*x - .054233*x + .55556);
            //var activityContrib=sens*treatment.insulin*(2/dia/60-(minAgo-peak)*2/dia/60/(60*dia-peak));
            var activityContrib=treatment.insulin*(2/dia/60-(minAgo-peak)*2/dia/60/(60*dia-peak));
        }
        else {
            var iobContrib=0;
            var activityContrib=0;
        }
        return {
            iobContrib: iobContrib,
            activityContrib: activityContrib
        };
    }
    else {
        return '';
    }
}

exports = module.exports = iobCalc;
