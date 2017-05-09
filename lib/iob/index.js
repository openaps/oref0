
var tz = require('moment-timezone');
var find_insulin = require('./history');
var calculate = require('./calculate');
var sum = require('./total');

function generate (inputs) {

    var treatments = find_insulin(inputs);

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
    //console.error(treatments[treatments.length-1]);
    treatments.forEach(function(treatment) {
        if (treatment.insulin && treatment.started_at) {
            lastBolusTime = Math.max(lastBolusTime,treatment.started_at);
            //console.error(treatment.insulin,treatment.started_at,lastBolusTime);
        }
        //if (treatment.insulin && treatment.started_at) { console.error(treatment.insulin,treatment.started_at,lastBolusTime); }
    });
    // predict IOB out to DIA plus 30m to account for any running temp basals
    for (i=0; i<((inputs.profile.dia*60)+30); i+=5){
        t = new Date(clock.getTime() + i*60000);
        //console.error(t);
        var iob = sum(opts, t);
        iobArray.push(iob);
    }
    //console.error(lastBolusTime);
    iobArray[0].lastBolusTime = lastBolusTime;
    return iobArray;
}

exports = module.exports = generate;
