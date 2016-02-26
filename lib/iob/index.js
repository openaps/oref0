
var tz = require('timezone');
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
    var clock = new Date(tz(inputs.clock));

    for (i=0; i<inputs.profile.dia*60; i+=5){
        t = new Date(clock.getTime() + i*60000);
        //console.error(t);
        var iob = sum(opts, t);
        iobArray.push(iob);
    }
    return iobArray;
}

exports = module.exports = generate;
