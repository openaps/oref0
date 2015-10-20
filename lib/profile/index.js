
var basal = require('./basal');
var targets = require('./targets');
var isf = require('./isf');

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
  if (inputs.settings.insulin_action_curve) {
    profile.dia =  pumpsettings_data.insulin_action_curve;
  }

  if (inputs.max_iob) {
    profile.max_iob = inputs.max_iob;
  }

  profile.current_basal = basal.basalLookup(inputs.basals);
  profile.max_daily_basal = basal.maxDailyBasal(inputs);
  profile.max_basal = basal.maxBasalLookup(inputs);

  var range = targets.bgTargetsLookup(inputs);
  profile.min_bg = range.min_bg;
  profile.max_bg = range.max_bg;
  profile.sens = isf.isfLookup(inputs);

  return profile;
}


generate.defaults = defaults;
exports = module.exports = generate;

