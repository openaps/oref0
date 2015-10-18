
var tz = require('timezone');
var find_insulin = require('./history');
var calculate = require('./calculate');
var sum = require('./total');

function generate (inputs) {

  var treatments = find_insulin(inputs);
  treatments.sort(function (a, b) { return a.date > b.date });

  var opts = {
    treatments: treatments
  , profile: inputs.profile
  , calculate: calculate
  };

  var clock = new Date(tz(inputs.clock));

  var iob = sum(opts, clock);
  return iob;
}

exports = module.exports = generate;
