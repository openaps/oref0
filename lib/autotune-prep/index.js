
// Prep step before autotune.js can run; pulls in meal (carb) data and calls categorize.js 

var tz = require('moment-timezone');
var find_meals = require('../meal/history');
var categorize = require('./categorize');

function generate (inputs) {

  //console.error(inputs);
  var treatments = find_meals(inputs);

  var opts = {
    treatments: treatments
  , profile: inputs.profile
  , pumpHistory: inputs.history
  , glucose: inputs.glucose
  //, prepped_glucose: inputs.prepped_glucose
  , basalprofile: inputs.profile.basalprofile
  , pumpbasalprofile: inputs.pumpprofile.basalprofile
  , categorize_uam_as_basal: inputs.categorize_uam_as_basal
  };

  var autotune_prep_output = categorize(opts);

  if (inputs.tune_insulin_curve) {
    if (opts.profile.curve === 'bilinear') {
      console.error('--tune-insulin-curve is set but only valid for exponential curves');
    } else {
      let minDeviations = 1000000;
      let newDIA = 0;
      let diaDeviations = [];
      let peakDeviations = [];
      let currentDIA = opts.profile.dia;
      let currentPeak = opts.profile.insulinPeakTime;

      let consoleError = console.error;
      console.error = function() {};

      let startDIA=currentDIA - 2;
      let endDIA=currentDIA + 2;
      for (let dia=startDIA; dia <= endDIA; ++dia) {
        let deviations = 0;

        opts.profile.dia = dia;

        let curve_output = categorize(opts);
        let basalGlucose = curve_output.basalGlucoseData;

        for (let hour=0; hour < 24; ++hour) {
          for (var i=0; i < basalGlucose.length; ++i) {
            var BGTime;

            if (basalGlucose[i].date) {
              BGTime = new Date(basalGlucose[i].date);
            } else if (basalGlucose[i].displayTime) {
              BGTime = new Date(basalGlucose[i].displayTime.replace('T', ' '));
            } else if (basalGuclose[i].dateString) {
              BGTime = new Date(basalGlucose[i].dateString);
            } else {
              consoleError("Could not determine last BG time");
            }

            var myHour = BGTime.getHours();
            if (hour == myHour) {
              //console.error(basalGlucose[i].deviation);
              deviations += Math.pow(parseFloat(basalGlucose[i].deviation), 2);
            }
          }
        }

        consoleError('DIA', dia, 'total sum squared deviations:', Math.round(deviations*1000)/1000, '(mg/dL)^2');
        diaDeviations.push({dia: dia, devSquared: Math.round(deviations*1000)/1000});
        autotune_prep_output.diaDeviations = diaDeviations;

        if (deviations < minDeviations) {
          minDeviations = Math.round(deviations*1000)/1000;
          newDIA = dia;
        }
      }

      consoleError('Optimum DIA', newDIA, 'total sum squared deviations:', minDeviations, '(mg/dL)^2');
      //consoleError(diaDeviations);

      minDeviations = 1000000;

      let newPeak = 0;
      opts.profile.dia = currentDIA;
      //consoleError(opts.profile.useCustomPeakTime, opts.profile.insulinPeakTime);
      if ( ! opts.profile.useCustomPeakTime && opts.profile.curve === "ultra-rapid" ) {
        opts.profile.insulinPeakTime = 55;
      }
      opts.profile.useCustomPeakTime = true;

      let startPeak=opts.profile.insulinPeakTime - 10;
      let endPeak=opts.profile.insulinPeakTime + 10;
      for (let peak=startPeak; peak <= endPeak; peak=(peak+5)) {
        let deviations = 0;

        opts.profile.insulinPeakTime = peak;


        let curve_output = categorize(opts);
        let basalGlucose = curve_output.basalGlucoseData;

        for (let hour=0; hour < 24; ++hour) {
          for (var i=0; i < basalGlucose.length; ++i) {
            var BGTime;

            if (basalGlucose[i].date) {
              BGTime = new Date(basalGlucose[i].date);
            } else if (basalGlucose[i].displayTime) {
              BGTime = new Date(basalGlucose[i].displayTime.replace('T', ' '));
            } else if (basalGuclose[i].dateString) {
              BGTime = new Date(basalGlucose[i].dateString);
            } else {
              consoleError("Could not determine last BG time");
            }

            var myHour = BGTime.getHours();
            if (hour == myHour) {
              //console.error(basalGlucose[i].deviation);
              deviations += Math.pow(parseFloat(basalGlucose[i].deviation), 2);
            }
          }
        }

        consoleError('insulinPeakTime', peak, 'total sum squared deviations:', Math.round(deviations*1000)/1000, '(mg/dL)^2');
        peakDeviations.push({peak: peak, devSquared: Math.round(deviations*1000)/1000});

        if (deviations < minDeviations) {
          minDeviations = Math.round(deviations*1000)/1000;
          newPeak = peak;
        }
      }

      consoleError('Optimum insulinPeakTime', newPeak, 'total sum squared deviations:', minDeviations, '(mg/dL)^2');
      //consoleError(peakDeviations);
      autotune_prep_output.peakDeviations = peakDeviations;

      console.error = consoleError;
    }
  }

  return autotune_prep_output;
}

exports = module.exports = generate;
