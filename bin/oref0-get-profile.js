#!/usr/bin/env node
'use strict';

/*
  Get Basal Information

  Released under MIT license. See the accompanying LICENSE.txt file for
  full terms and conditions

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.

*/

var fs = require('fs');
var generate = require('../lib/profile/');
var shared_node_utils = require('./oref0-shared-node-utils');
var console_error = shared_node_utils.console_error;
var console_log = shared_node_utils.console_log;
var process_exit = shared_node_utils.process_exit;
var initFinalResults = shared_node_utils.initFinalResults;

function exportDefaults (final_result) {
	var defaults = generate.displayedDefaults(final_result);
	console_log(final_result, JSON.stringify(defaults, null, '\t'));
}

function updatePreferences (final_result, prefs) {
	var defaults = generate.displayedDefaults(final_result);
	
	// check for any displayedDefaults missing from current prefs and add from defaults
	
    for (var pref in defaults) {
      if (defaults.hasOwnProperty(pref) && !prefs.hasOwnProperty(pref)) {
        prefs[pref] = defaults[pref];
      }
    }

    console_log(final_result, JSON.stringify(prefs, null, '\t'));
}

var oref0_get_profile = function oref0_get_profile(final_result, argv_params) {  
    var argv = require('yargs')(argv_params)
      .usage("$0 <pump_settings.json> <bg_targets.json> <insulin_sensitivities.json> <basal_profile.json> [<preferences.json>] [<carb_ratios.json>] [<temptargets.json>] [--model <model.json>] [--autotune <autotune.json>] [--exportDefaults] [--updatePreferences <preferences.json>]")
      .option('model', {
        alias: 'm',
        describe: "Pump model response",
        nargs: 1,
        default: false
      })
      .option('autotune', {
        alias: 'a',
        describe: "Autotuned profile.json",
        nargs: 1,
        default: false
      })
      .strict(true)
      .help('help')
      .option('exportDefaults', {
        describe: "Show typically-adjusted default preference values",
        boolean: true,
        default: false
      })
      .option('updatePreferences', {
        describe: "Check for any keys missing from current prefs and add from defaults. Requires preference file argument.",
        nargs: 1,
        default: false
      })

    var params = argv.argv;

    if (!params.exportDefaults && !params.updatePreferences) {
      if (params._.length < 4 || params._.length > 7) {
        argv.showHelp();
        process_exit(final_result, 1);
        return;
      }
    }

    var pumpsettings_input = params._[0];

    if (params.exportDefaults) {
        exportDefaults(final_result);
        return;
    }
    if (params.updatePreferences) {
        var preferences = {};
        var cwd = process.cwd()
        preferences = JSON.parse(fs.readFileSync(cwd + '/' + params.updatePreferences));
        updatePreferences(final_result, preferences);
        return;
    }

    var bgtargets_input = params._[1]
    var isf_input = params._[2]
    var basalprofile_input = params._[3]
    var preferences_input = params._[4]
    var carbratio_input = params._[5]
    var temptargets_input = params._[6]
    var model_input = params.model;
    var autotune_input = params.autotune;

    cwd = process.cwd()
    var pumpsettings_data = JSON.parse(fs.readFileSync(cwd + '/' + pumpsettings_input));
    var bgtargets_data = JSON.parse(fs.readFileSync(cwd + '/' + bgtargets_input));
    if (bgtargets_data.units !== 'mg/dL') {
        if (bgtargets_data.units === 'mmol/L') {
            for (var i = 0, len = bgtargets_data.targets.length; i < len; i++) {
                bgtargets_data.targets[i].high = bgtargets_data.targets[i].high * 18;
                bgtargets_data.targets[i].low = bgtargets_data.targets[i].low * 18;
            }
            bgtargets_data.units = 'mg/dL';
        } else {
            console_log(final_result, 'BG Target data is expected to be expressed in mg/dL or mmol/L.'
                 , 'Found', bgtargets_data.units, 'in', bgtargets_input, '.');
            process_exit(final_result, 2);
            return;
        }
    }
    
    var isf_data = JSON.parse(fs.readFileSync(cwd + '/' + isf_input));
    if (isf_data.units !== 'mg/dL') {
        if (isf_data.units === 'mmol/L') {
            for (i = 0, len = isf_data.sensitivities.length; i < len; i++) {
                isf_data.sensitivities[i].sensitivity = isf_data.sensitivities[i].sensitivity * 18;
            }
            isf_data.units = 'mg/dL';
        } else {
            console_log(final_result, 'ISF is expected to be expressed in mg/dL or mmol/L.'
                    , 'Found', isf_data.units, 'in', isf_input, '.');
            process_exit(final_result, 2);
            return;
        }
    }
    var basalprofile_data = JSON.parse(fs.readFileSync(cwd + '/' + basalprofile_input));

    preferences = {};
    if (typeof preferences_input !== 'undefined') {
        preferences = JSON.parse(fs.readFileSync(cwd + '/' + preferences_input));
    }

    var model_data = { }
    if (params.model) {
      try {
        var model_string = fs.readFileSync(model_input, 'utf8');
        model_data = model_string.replace(/"/gi, '');
      } catch (e) {
        var msg = { error: e, msg: "Could not parse model_data", file: model_input};
        console_error(final_result, msg.msg);
        console_log(final_result, JSON.stringify(msg));
        process_exit(final_result, 1);
        return;
      }
    }
    var autotune_data = { }
    if (params.autotune) {
      try {
        autotune_data = JSON.parse(fs.readFileSync(autotune_input, 'utf8'));

      } catch (e) {
        msg = { error: e, msg: "Could not parse autotune_data", file: autotune_input};
        console_error(final_result, msg.msg);
        // Continue and output a non-autotuned profile if we don't have autotune_data
        //console.log(JSON.stringify(msg));
        //process.exit(1);
      }
    }

    var carbratio_data = { };
    //console.log("carbratio_input",carbratio_input);
    if (typeof carbratio_input !== 'undefined') {
        try {
            carbratio_data = JSON.parse(fs.readFileSync(carbratio_input, 'utf8'));

        } catch (e) {
            msg = { error: e, msg: "Could not parse carbratio_data. Feature Meal Assist enabled but cannot find required carb_ratios.", file: carbratio_input };
            console_error(final_result, msg.msg);
            console.log(final_result, JSON.stringify(msg));
            process_exit(final_result, 1);
            return;
        }
        var errors = [ ];

        if (!(carbratio_data.schedule && carbratio_data.schedule[0].start && carbratio_data.schedule[0].ratio)) {
          errors.push({msg: "Carb ratio data should have an array called schedule with a start and ratio fields.", file: carbratio_input, data: carbratio_data});
        } else {
        }
        if (carbratio_data.units !== 'grams' && carbratio_data.units !== 'exchanges')  {
          errors.push({msg: "Carb ratio should have units field set to 'grams' or 'exchanges'.", file: carbratio_input, data: carbratio_data});
        }
        if (errors.length) {

          errors.forEach(function (msg) {
            console_error(final_result, msg.msg);
          });
          console_log(final_result, JSON.stringify(errors));
          process_exit(final_result, 1);
          
          return;
        }
    }
    var temptargets_data = { };
    if (typeof temptargets_input !== 'undefined') {
        try {
            temptargets_data = JSON.parse(fs.readFileSync(temptargets_input, 'utf8'));
        } catch (e) {
            console_error(final_result, "Could not parse temptargets_data.");
        }
    }

    //console.log(carbratio_data);
    var inputs = { };

    //add all preferences to the inputs
    for (var pref in preferences) {
      if (preferences.hasOwnProperty(pref)) {
        inputs[pref] = preferences[pref];
      }
    }

    //make sure max_iob is set or default to 0
    inputs.max_iob = inputs.max_iob || 0;

    //set these after to make sure nothing happens if they are also set in preferences
    inputs.settings = pumpsettings_data;
    inputs.targets = bgtargets_data;
    inputs.basals = basalprofile_data;
    inputs.isf = isf_data;
    inputs.carbratio = carbratio_data;
    inputs.temptargets = temptargets_data;
    inputs.model = model_data;
    inputs.autotune = autotune_data;

    if (autotune_data) {
        if (autotune_data.basalprofile) { inputs.basals = autotune_data.basalprofile; }
        if (autotune_data.isfProfile) { inputs.isf = autotune_data.isfProfile; }
        if (autotune_data.carb_ratio) { inputs.carbratio.schedule[0].ratio = autotune_data.carb_ratio; }
    }
    var profile = generate(final_result, inputs);

    console_log(final_result, JSON.stringify(profile));

}

if (!module.parent) {
    var final_result = initFinalResults();
    // remove the first parameter.
    var command = process.argv;
    command.shift();
    command.shift();
    oref0_get_profile(final_result, command)

    console.log(final_result.stdout);
    if(final_result.err.length > 0) {
        console.error(final_result.err);
    }
    process.exit(final_result.return_val);
}

exports = module.exports = oref0_get_profile;
