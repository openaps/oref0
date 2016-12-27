
var tz = require('timezone');
var find_meals = require('oref0/lib/meal/history');
var sum = require('./total');

function generate (inputs) {

  //console.error(inputs);
  var treatments = find_meals(inputs);

  var opts = {
    treatments: treatments
  , profile: inputs.profile
  , pumphistory: inputs.history
  , glucose: inputs.glucose
  , prepped_glucose: inputs.prepped_glucose
  , basalprofile: inputs.profile.basalprofile
  };

  var autotune_prep_output = sum(opts);
  return autotune_prep_output;
}

exports = module.exports = generate;
