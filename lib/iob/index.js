
var tz = require('moment-timezone');
var find_insulin = require('./history');
var calculate = require('./calculate');
var sum = require('./total');

function generate (inputs, currentIOBOnly, treatments) {

    if (!treatments) {
        var treatments = find_insulin(inputs);
    }

    var opts = {
        treatments: treatments
    , profile: inputs.profile
    , calculate: calculate
    };

    var iobArray = [];
    //console.error(inputs.clock);
    if (! /(Z|[+-][0-2][0-9]:?[034][05])+/.test(inputs.clock) ) {
        console.error("Warning: clock input " + inputs.clock + " is unzoned; please pass clock-zoned.json instead");
    }
    var clock = new Date(tz(inputs.clock));

    var lastBolusTime = new Date(0).getTime(); //clock.getTime());
    var lastTemp = {};
    lastTemp.date = new Date(0).getTime(); //clock.getTime());
    //console.error(treatments[treatments.length-1]);
    treatments.forEach(function(treatment) {
        if (treatment.insulin && treatment.started_at) {
            lastBolusTime = Math.max(lastBolusTime,treatment.started_at);
            //console.error(treatment.insulin,treatment.started_at,lastBolusTime);
        } else if (typeof(treatment.rate) === 'number' && treatment.duration ) {
            if ( treatment.date > lastTemp.date ) {
                lastTemp = treatment;
                lastTemp.duration = Math.round(lastTemp.duration*100)/100;
            }

            //console.error(treatment.rate, treatment.duration, treatment.started_at,lastTemp.started_at)
        }
        //console.error(treatment.rate, treatment.duration, treatment.started_at,lastTemp.started_at)
        //if (treatment.insulin && treatment.started_at) { console.error(treatment.insulin,treatment.started_at,lastBolusTime); }
    });
    var iStop;
    if (currentIOBOnly) {
        // for COB calculation, we only need the zeroth element of iobArray
        iStop=1
    } else {
        // predict IOB out to 4h, regardless of DIA
        iStop=4*60;
    }
    for (i=0; i<iStop; i+=5){
        t = new Date(clock.getTime() + i*60000);
        //console.error(t);
        var iob = sum(opts, t);
        iobArray.push(iob);
    }
    //console.error(lastBolusTime);
    iobArray[0].lastBolusTime = lastBolusTime;
    iobArray[0].lastTemp = lastTemp;
    return iobArray;
}

exports = module.exports = generate;
