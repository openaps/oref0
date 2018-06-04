
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
      var minDeviations = 1000000;
      var newDIA = 0;
      var diaDeviations = [];
      var peakDeviations = [];
      var currentDIA = opts.profile.dia;
      var currentPeak = opts.profile.insulinPeakTime;

      var consoleError = console.error;
      console.error = function() {};

      var startDIA=currentDIA - 2;
      var endDIA=currentDIA + 2;
      for (var dia=startDIA; dia <= endDIA; ++dia) {
        var deviations = 0;
        var deviationsSq = 0;

        opts.profile.dia = dia;

        var curve_output = categorize(opts);
        var basalGlucose = curve_output.basalGlucoseData;

        for (var hour=0; hour < 24; ++hour) {
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
              deviations += parseFloat(basalGlucose[i].deviation);
              deviationsSq += Math.pow(parseFloat(basalGlucose[i].deviation), 2);
            }
          }
        }

        consoleError('insulinEndTime', dia, ', sum of deviations:', Math.round(deviations*1000)/1000, '(mg/dL), sum of squared deviations:', Math.round(deviationsSq*1000)/1000, '(mg/dL)^2');
        diaDeviations.push({
            dia: dia,
            deviations: Math.round(deviations*1000)/1000
            devSquared: Math.round(deviationsSq*1000)/1000
        });
        autotune_prep_output.diaDeviations = diaDeviations;

        deviations = Math.round(deviations*1000)/1000;
        if (deviations < minDeviations) {
          minDeviations = Math.round(deviations*1000)/1000;
          newDIA = dia;
        }
      }

      consoleError('Optimum insulinEndTime', newDIA, 'total sum squared deviations:', minDeviations, '(mg/dL)^2');
      //consoleError(diaDeviations);

      minDeviations = 1000000;

      var newPeak = 0;
      opts.profile.dia = currentDIA;
      //consoleError(opts.profile.useCustomPeakTime, opts.profile.insulinPeakTime);
      if ( ! opts.profile.useCustomPeakTime && opts.profile.curve === "ultra-rapid" ) {
        opts.profile.insulinPeakTime = 55;
      }
      opts.profile.useCustomPeakTime = true;

      var startPeak=opts.profile.insulinPeakTime - 10;
      var endPeak=opts.profile.insulinPeakTime + 10;
      for (var peak=startPeak; peak <= endPeak; peak=(peak+5)) {
        var deviations = 0;

        opts.profile.insulinPeakTime = peak;


        var curve_output = categorize(opts);
        var basalGlucose = curve_output.basalGlucoseData;

        for (var hour=0; hour < 24; ++hour) {
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

        deviations = Math.round(deviations*1000)/1000;
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
