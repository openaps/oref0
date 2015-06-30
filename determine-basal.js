

function get_last_glucose (data) {
  var one = data[0];
  var two = data[1];
  var o = {
    delta: one.glucose - two.glucose
  , glucose: one.glucose
  };
  return o;
}


if (!module.parent) {
  var iob_input = process.argv.slice(2,3).pop( )
  var temps_input = process.argv.slice(3,4).pop( )
  var glucose_input = process.argv.slice(4,5).pop( )
  if (!iob_input || !temps_input || !glucose_input) {
    console.log('usage: ', process.argv.slice(0, 2), '<iob.json> <current-temps.json> <glucose.json>');
    process.exit(1);
  }


  /*
  var _profile = {
    dia: dia, # Duration of Insulin Action (hours)
    , isf: isf, # Insulin Sensitivity Factor (mg/dL/U)
    , bgTargetMin: bgTargetMin, # low end of BG Target range
    , bgTargetMax: bgTargetMax, # high end of BG Target range
    , bgSuspend: bgTargetMin - 30, # temp to 0 if dropping below this BG
    , maxBasal: maxBasal # pump's maximum basal setting
    // , #ic: ic, # Insulin to Carb Ratio (g/U)
    // , #csf: isf / ic, # Carb Sensitivity Factor (mg/dL/g)
    , basals: basals # Basal Schedule (array of [start time of day, rate (U/hr)])
  };
  */
  var profile = {
    // xxx get from pump/schedule, etc
    basal: 0.9333333333333334
    ,carbratio: 13
    ,carbs_hr: 30
    ,dia: 3
    ,max_bg: 140
    ,max_iob: 4
    ,min_bg: 120
    ,sens: 45
    ,target_bg: 120
    ,type: "current"
  };
  var glucose_data = require('./' + glucose_input);
  var temps_data = require('./' + temps_input);
  var iob_data = require('./' + iob_input);
  var glucose_status = get_last_glucose(glucose_data);

  var eventualBG = glucose_status.glucose - (iob_data.iob * profile.sens);
  // console.log("EVENTUAL BG", eventualBG);
  var requestedTemp = {
    'temp': 'absolute'
  };
  if ((glucose_status.delta > 0 && eventualBG <= profile.target_bg) || (glucose_status.delta < 0 && eventualBG >= profile.target_bg)) {
    // cancel temp
    requestedTemp.duration = 0;
    requestedTemp.rate = 0;
    //requestedTemp.temp = 'absolute';
  } else if (eventualBG < profile.target_bg) {

    var insulinReq = Math.max(0, (profile.target_bg - eventualBG) / profile.sens);
    var rate = profile.basal - (2 * insulinReq);
    requestedTemp.duration = 30;
    requestedTemp.rate = rate;
    //requestedTemp.temp = 'absolute';

  } else if (eventualBG > profile.target_bg) {
    var insulinReq = (profile.target_bg - eventualBG) / profile.sens;
    var rate = profile.basal - (2 * insulinReq);
    requestedTemp.duration = 30;
    requestedTemp.rate = rate;
    //requestedTemp.temp = 'absolute';
  }

  console.log(JSON.stringify(requestedTemp));

}
