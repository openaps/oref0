
var basal = require('./basal');
var targets = require('./targets');
var isf = require('./isf');
var carb_ratios = require('./carbs');

function defaults ( ) {
    var profile = {        
          max_iob: 0 // if max_iob is not provided, never give more insulin than the pump would have
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
    console.error("Error: DIA of",profile.dia,"is not supported");
    return -1;
  }

  if (inputs.max_iob) {
    profile.max_iob = inputs.max_iob;
  }

  profile.current_basal = basal.basalLookup(inputs.basals);
  min_daily_basal = basal.minDailyBasal(inputs);
  profile.max_daily_basal = basal.maxDailyBasal(inputs);
  if (profile.max_daily_basal > 3 * min_daily_basal) {
    console.error("Error: Max daily basal of",profile.max_daily_basal,"cannot be more than 3x min daily basal of",min_daily_basal);
    return -1;
  }
  profile.max_basal = basal.maxBasalLookup(inputs);
  if (profile.basal < 0.1) {
    console.error("Error: Basal of",profile.basal,"is not supported");
    return -1;
  }

  var range = targets.bgTargetsLookup(inputs);
  profile.min_bg = range.min_bg;
  profile.max_bg = range.max_bg;
  profile.sens = isf.isfLookup(inputs);
  if (profile.sens < 5) {
    console.error("Error: ISF of",profile.sens,"is not supported");
    return -1;
  }
  if (typeof(inputs.carbratio) != "undefined") {
    profile.carb_ratio = carb_ratios.carbRatioLookup(inputs);
  }

  return profile;
}


generate.defaults = defaults;
exports = module.exports = generate;

