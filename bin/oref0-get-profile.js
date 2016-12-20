#!/usr/bin/env node

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

var generate = require('oref0/lib/profile/');
function usage ( ) {
        console.log('usage: ', process.argv.slice(0, 2), '<pump_settings.json> <bg_targets.json> <insulin_sensitivities.json> <basal_profile.json> [<preferences.json>] [<carb_ratios.json>] [<temptargets.json>] [--model model.json]');
}

function exportDefaults () {
	var defaults = generate.defaults();
	console.log(JSON.stringify(defaults, null, '\t'));
}

function updatePreferences (prefs) {
	var defaults = generate.defaults();
	
	// check for any keys missing from current prefs and add from defaults
	
    for (var pref in defaults) {
      if (defaults.hasOwnProperty(pref) && !prefs.hasOwnProperty(pref)) {
        prefs[pref] = defaults[pref];
      }
    }

	console.log(JSON.stringify(prefs, null, '\t'));
}

if (!module.parent) {
    
    var argv = require('yargs')
      .usage("$0 pump_settings.json bg_targets.json insulin_sensitivities.json basal_profile.json [preferences.json] [<carb_ratios.json>] [<temptargets.json>] [--model model.json]")
      .option('model', {
        alias: 'm',
        describe: "Pump model response",
        default: false
      })
      .strict(true)
      .help('help')
      .option('exportDefaults', {
        describe: "Show default preference values",
        default: false
      })
      .option('updatePreferences', {
        describe: "Check for any keys missing from current prefs and add from defaults",
        default: false
      })

    var params = argv.argv;
    var pumpsettings_input = params._.slice(0, 1).pop()
    if ([null, '--help', '-h', 'help'].indexOf(pumpsettings_input) > 0) {
      usage( );
      process.exit(0);
    }
    if (params.exportDefaults) {
        exportDefaults();
        process.exit(0);
    }
    if (params.updatePreferences) {
        var preferences = {};
        var cwd = process.cwd()
        preferences = require(cwd + '/' + params.updatePreferences);
        updatePreferences(preferences);
        process.exit(0);
    }

    var bgtargets_input = params._.slice(1, 2).pop()
    var isf_input = params._.slice(2, 3).pop()
    var basalprofile_input = params._.slice(3, 4).pop()
    var preferences_input = params._.slice(4, 5).pop()
    var carbratio_input = params._.slice(5, 6).pop()
    var temptargets_input = params._.slice(6, 7).pop()
    var model_input = params.model;

    if (!pumpsettings_input || !bgtargets_input || !isf_input || !basalprofile_input) {
        usage( );
        process.exit(1);
    }

    var cwd = process.cwd()
    var pumpsettings_data = require(cwd + '/' + pumpsettings_input);
    var bgtargets_data = require(cwd + '/' + bgtargets_input);
    if (bgtargets_data.units !== 'mg/dL') {
      console.log('BG Target data is expected to be expressed in mg/dL.'
                 , 'Found', bgtargets_data.units, 'in', bgtargets_input, '.');
      process.exit(2);
    }
    var isf_data = require(cwd + '/' + isf_input);
    if (isf_data.units !== 'mg/dL') {
      console.log('ISF is expected to be expressed in mg/dL.'
                 , 'Found', isf_data.units, 'in', isf_input, '.');
      process.exit(2);
    }
    var basalprofile_data = require(cwd + '/' + basalprofile_input);

    var preferences = {};
    if (typeof preferences_input != 'undefined') {
        preferences = require(cwd + '/' + preferences_input);
    }
    var fs = require('fs');

    var model_data = { }
    if (params.model) {
      try {
        model_string = fs.readFileSync(model_input, 'utf8');
        model_data = model_string.replace(/\"/gi, '');
      } catch (e) {
        var msg = { error: e, msg: "Could not parse model_data", file: model_input};
        console.error(msg.msg);
        console.log(JSON.stringify(msg));
        process.exit(1);
      }
    }

    var carbratio_data = { };
    //console.log("carbratio_input",carbratio_input);
    if (typeof carbratio_input != 'undefined') {
        try {
            carbratio_data = JSON.parse(fs.readFileSync(carbratio_input, 'utf8'));

        } catch (e) {
            var msg = { error: e, msg: "Could not parse carbratio_data. Feature Meal Assist enabled but cannot find required carb_ratios.", file: carbratio_input };
            console.error(msg.msg);
            console.log(JSON.stringify(msg));
            process.exit(1);
        }
        var errors = [ ];

        if (!(carbratio_data.schedule && carbratio_data.schedule[0].start && carbratio_data.schedule[0].ratio)) {
          errors.push({msg: "Carb ratio data should have an array called schedule with a start and ratio fields.", file: carbratio_input, data: carbratio_data});
        } else {
        }
        if (carbratio_data.units != 'grams' && carbratio_data.units != 'exchanges')  {
          errors.push({msg: "Carb ratio should have units field set to 'grams' or 'exchanges'.", file: carbratio_input, data: carbratio_data});
        }
        if (errors.length) {

          errors.forEach(function (msg) {
            console.error(msg.msg);
          });
          console.log(JSON.stringify(errors));
          process.exit(1);
        }
    }
    var temptargets_data = { };
    if (typeof temptargets_input != 'undefined') {
        try {
            temptargets_data = JSON.parse(fs.readFileSync(temptargets_input, 'utf8'));
        } catch (e) {
            //console.error("Could not parse temptargets_data.");
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

    var profile = generate(inputs);

    console.log(JSON.stringify(profile));

}
