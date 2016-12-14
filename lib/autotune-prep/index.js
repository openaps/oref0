
var tz = require('timezone');
var find_meals = require('oref0/lib/meal/history');
var sum = require('./total');

function generate (inputs) {

  var treatments = find_meals(inputs);

  var opts = {
    treatments: treatments
  , profile: inputs.profile
  , pumphistory: inputs.history
  , glucose: inputs.glucose
  , basalprofile: inputs.basalprofile
  };

  var clock = new Date(tz(inputs.clock));

  var autotune-prep-output = sum(opts, clock);
  return autotune-prep-output;
}

exports = module.exports = generate;
