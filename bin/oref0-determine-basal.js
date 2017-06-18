#!/usr/bin/env node

/*
  Determine Basal

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

/* istanbul ignore next */
if (!module.parent) {
    var determinebasal = init();

    var argv = require('yargs')
      .usage("$0 iob.json currenttemp.json glucose.json profile.json [[--auto-sens] autosens.json] [meal.json] [--reservoir reservoir.json]")
      .option('auto-sens', {
        alias: 'a',
        describe: "Auto-sensitivity configuration",
        default: true

      })
      .option('reservoir', {
        alias: 'r',
        describe: "Reservoir status file for SuperMicroBolus mode (oref1)",
        default: false

      })
      .option('meal', {
        describe: "json doc describing meals",
        default: true

      })
      .option('missing-auto-sens-ok', {
        describe: "If auto-sens data is missing, try anyway.",
        default: true

      })
      .option('missing-meal-ok', {
        describe: "If meal data is missing, try anyway.",
        default: true

      })
      .option('microbolus', {
        describe: "Enable SuperMicroBolus mode (oref1)",
        default: false

      })
      // error and show help if some other args given
      .strict(true)
      .help('help')
    ;
    function usage ( ) {
      argv.showHelp( );
    }

    var params = argv.argv;
    var errors = [ ];
    var warnings = [ ];

    var iob_input = params._.slice(0, 1).pop();
    if ([null, '--help', '-h', 'help'].indexOf(iob_input) > 0) {

      usage( );
      process.exit(0)
    }
    var currenttemp_input = params._.slice(1, 2).pop();
    var glucose_input = params._.slice(2, 3).pop();
    var profile_input = params._.slice(3, 4).pop();
    var meal_input = params._.slice(4, 5).pop();
    var autosens_input = params.autoSens;
    if (params._.length > 5) {
      autosens_input = params.autoSens ? params._.slice(4, 5).pop() : false;
      meal_input = params._.slice(5, 6).pop();
    }
    if (params.meal && params.meal !== true && !meal_input) {
      meal_input = params.meal;
    }
    var reservoir_input = params.reservoir;

    if (!iob_input || !currenttemp_input || !glucose_input || !profile_input) {
        usage( );
        process.exit(1);
    }

    var fs = require('fs');
    try {
        var cwd = process.cwd();
        var glucose_data = require(cwd + '/' + glucose_input);
        var currenttemp = require(cwd + '/' + currenttemp_input);
        var iob_data = require(cwd + '/' + iob_input);
        var profile = require(cwd + '/' + profile_input);
        var glucose_status = determinebasal.getLastGlucose(glucose_data);
    } catch (e) {
        return console.error("Could not parse input data: ", e);
    }

    //attempting to provide a check for autotune
    //if autotune directory does not exist, SMB/oref1 should not be able to run

    // console.error("Printing this so you know it's getting to the check for autotune.")

    //printing microbolus before attempting check
    //console.error("Microbolus var is currently set to: ",params['microbolus']);

    if (params['microbolus']) {
        if (fs.existsSync("autotune")) {
            console.error("Autotune exists! Hoorah! You can use microbolus-related features.")
        } else {
            console.error("Warning: Autotune has not been run. All microboluses will be disabled until you manually run autotune or add it to run nightly in your loop.");
            params['microbolus'] = false;
            //console.error("Microbolus var is currently set to: ",params['microbolus']);
        }
    }

    //console.log(carbratio_data);
    var meal_data = { };
    //console.error("meal_input",meal_input);
    if (meal_input && typeof meal_input != 'undefined') {
        try {
            meal_data = JSON.parse(fs.readFileSync(meal_input, 'utf8'));
            console.error(JSON.stringify(meal_data));
        } catch (e) {
            var msg = {
              msg: "Optional feature Meal Assist enabled, but could not read required meal data."
            , file: meal_input
            , error: e
            };
            console.error(msg.msg);
            // console.log(JSON.stringify(msg));
            if (!params['missing-meal-ok']) {
              warnings.push(msg);
            }
            // process.exit(1);
        }
    }
    //if (meal_input) { meal_data = require(cwd + '/' + meal_input); }

    //console.error(autosens_input);
    var autosens_data = null;
    if (autosens_input) {
      // { "ratio":1 };
      autosens_data = { "ratio": 1 };
      if (autosens_input !== true && autosens_input.length) {
        try {
            autosens_data = JSON.parse(fs.readFileSync(autosens_input, 'utf8'));
            //console.error(JSON.stringify(autosens_data));
        } catch (e) {
            var msg = {
              msg: "Optional feature Auto Sensitivity enabled.  Could not find specified auto-sens: " + autosens_input
            , error: e
            };
            console.error(msg.msg);
            console.error(e);
            // console.log(JSON.stringify(msg));
            if (!params['missing-auto-sens-ok']) {
              errors.push(msg);
            }
            // process.exit(1);
        }
      }
    }
    var reservoir_data = null;
    if (reservoir_input && typeof reservoir_input != 'undefined') {
        try {
            reservoir_data = fs.readFileSync(reservoir_input, 'utf8');
            //console.error(reservoir_data);
        } catch (e) {
            var msg = {
              msg: "Warning: Could not read required reservoir data from "+reservoir_input+"."
            , file: reservoir_input
            , error: e
            };
            console.error(msg.msg);
        }
    }

    //if old reading from Dexcom do nothing

    var systemTime = new Date();
    var bgTime;
    if (glucose_data[0].display_time) {
        bgTime = new Date(glucose_data[0].display_time.replace('T', ' '));
    } else if (glucose_data[0].dateString) {
        bgTime = new Date(glucose_data[0].dateString);
    } else { console.error("Could not determine last BG time"); }
    var minAgo = (systemTime - bgTime) / 60 / 1000;

    if (warnings.length) {
      console.error(JSON.stringify(warnings));
    }

    if (errors.length) {
      console.log(JSON.stringify(errors));
      process.exit(1);
    }

    if (minAgo > 10 || minAgo < -5) { // Dexcom data is too old, or way in the future
        var reason = "BG data is too old (it's probably this), or clock set incorrectly.  The last BG data was read at "+bgTime+" but your system time currently is "+systemTime;
        console.error(reason);
        var msg = {reason: reason }
        console.log(JSON.stringify(msg));
        // errors.push(msg);
        process.exit(1);
    }


    if (typeof(iob_data.length) && iob_data.length > 1) {
        console.error(JSON.stringify(iob_data[0]));
    } else {
        console.error(JSON.stringify(iob_data));
    }

    console.error(JSON.stringify(glucose_status));
    console.error(JSON.stringify(currenttemp));
    //console.error(JSON.stringify(profile));

    var tempBasalFunctions = require('oref0/lib/basal-set-temp');

    rT = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile, autosens_data, meal_data, tempBasalFunctions, params['microbolus'], reservoir_data);

    if(typeof rT.error === 'undefined') {
        console.log(JSON.stringify(rT));
    } else {
        console.error(rT.error);
    }

}

function init() {

    var determinebasal = {
        name: 'determine-basal'
        , label: "OpenAPS Determine Basal"
    };

    determinebasal.getLastGlucose = require('oref0/lib/glucose-get-last');
    determinebasal.determine_basal = require('oref0/lib/determine-basal/determine-basal');
    return determinebasal;

}
module.exports = init;
