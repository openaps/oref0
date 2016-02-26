
var basal = require('./basal');
var targets = require('./targets');
var isf = require('./isf');
var carb_ratios = require('./carbs');

function defaults ( ) {
    var profile = {        
          max_iob: 0 // if max_iob.json is not profided, never give more insulin than the pump would have
        // , dia: pumpsettings_data.insulin_action_curve        
        , type: "current"
    };
    return profile;
}

function generate (inputs, opts) {
  var profile = opts && opts.type ? opts : defaults( );

  var pumpsettings_data = inputs.settings;
  if (inputs.settings.insulin_action_curve > 1) {
    profile.dia =  pumpsettings_data.insulin_action_curve;
  } else {
    console.error("DIA of",profile.dia,"is not supported");
    return -1;
  }

  if (inputs.max_iob) {
    profile.max_iob = inputs.max_iob;
  }

  profile.current_basal = basal.basalLookup(inputs.basals);
  profile.max_daily_basal = basal.maxDailyBasal(inputs);
  profile.max_basal = basal.maxBasalLookup(inputs);
  if (profile.basal < 0.1) {
    console.error("max_basal of",profile.max_basal,"is not supported");
    return -1;
  }

  var range = targets.bgTargetsLookup(inputs);
  profile.min_bg = range.min_bg;
  profile.max_bg = range.max_bg;
  profile.sens = isf.isfLookup(inputs);
  if (profile.sens < 5) {
    console.error("ISF of",profile.sens,"is not supported");
    return -1;
  }
  if (typeof(inputs.carbratio) != "undefined") {
    profile.carb_ratio = carb_ratios.carbRatioLookup(inputs);
  }

  return profile;
}


generate.defaults = defaults;
exports = module.exports = generate;

