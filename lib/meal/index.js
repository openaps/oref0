
var tz = require('timezone');
var find_meals = require('./history');
//var calculate = require('./calculate');
var sum = require('./total');

function generate (inputs) {

  var treatments = find_meals(inputs);

  var opts = {
    treatments: treatments
  , profile: inputs.profile
  //, calculate: calculate
  };

  var clock = new Date(tz(inputs.clock));

  var meal_data = sum(opts, clock);
  return meal_data;
}

exports = module.exports = generate;
