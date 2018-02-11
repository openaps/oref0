#!/usr/bin/env node

/*
  oref0 autotuning data prep tool

  Collects and divides up glucose data for periods dominated by carb absorption,
  correction insulin, or basal insulin, and adds in avgDelta and deviations,
  for use in oref0 autotuning algorithm

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

var generate = require('oref0/lib/autotune-prep');
function usage ( ) {
        console.error('usage: ', process.argv.slice(0, 2), '<pumphistory.json> <profile.json> <glucose.json> [pumpprofile.json] [carbhistory.json] [--categorize_uam_as_basal]');
}

if (!module.parent) {
    var pumphistory_input = process.argv[2];
    if ([null, '--help', '-h', 'help'].indexOf(pumphistory_input) > 0) {
      usage( );
      process.exit(0);
    }
    var profile_input = process.argv[3];
    var glucose_input = process.argv[4];
    var pumpprofile_input = process.argv[5];
    var carb_input = process.argv[6];
    var categorize_uam_as_basal_arg = process.argv[7];

    var categorize_uam_as_basal = false;

    if ( !pumphistory_input || !profile_input || !glucose_input ) {
        usage( );
        console.log('{ "error": "Insufficient arguments" }');
        process.exit(1);
    }

    if (carb_input === '--categorize_uam_as_basal') {
        categorize_uam_as_basal = true;
        carb_input = undefined;
    } else if (categorize_uam_as_basal_arg === '--categorize_uam_as_basal') {
        categorize_uam_as_basal = true;
    } else if (typeof categorize_uam_as_basal_arg !== 'undefined') {
        usage( );
        process.exit(1);
    }

    var fs = require('fs');
    try {
        var pumphistory_data = JSON.parse(fs.readFileSync(pumphistory_input, 'utf8'));
        var profile_data = JSON.parse(fs.readFileSync(profile_input, 'utf8'));
    } catch (e) {
        console.log('{ "error": "Could not parse input data" }');
        return console.error("Could not parse input data: ", e);
    }

    var pumpprofile_data = { };
    if (typeof pumpprofile_input != 'undefined') {
        try {
            pumpprofile_data = JSON.parse(fs.readFileSync(pumpprofile_input, 'utf8'));
        } catch (e) {
            console.error("Warning: could not parse "+pumpprofile_input);
        }
    }

    // disallow impossibly low carbRatios due to bad decoding
    if ( typeof(profile_data.carb_ratio) == 'undefined' || profile_data.carb_ratio < 2 ) {
        if ( typeof(pumpprofile_data.carb_ratio) == 'undefined' || pumpprofile_data.carb_ratio < 2 ) {
            console.log('{ "carbs": 0, "mealCOB": 0, "reason": "carb_ratios ' + profile_data.carb_ratio + ' and ' + pumpprofile_data.carb_ratio + ' out of bounds" }');
            return console.error("Error: carb_ratios " + profile_data.carb_ratio + ' and ' + pumpprofile_data.carb_ratio + " out of bounds");
        } else {
            profile_data.carb_ratio = pumpprofile_data.carb_ratio;
        }
    }

    try {
        var glucose_data = JSON.parse(fs.readFileSync(glucose_input, 'utf8'));
    } catch (e) {
        console.error("Warning: could not parse "+glucose_input);
    }

    var carb_data = { };
    if (typeof carb_input != 'undefined') {
        try {
            carb_data = JSON.parse(fs.readFileSync(carb_input, 'utf8'));
        } catch (e) {
            console.error("Warning: could not parse "+carb_input);
        }
    }

    var inputs = {
        history: pumphistory_data
    , profile: profile_data
    , pumpprofile: pumpprofile_data
    , carbs: carb_data
    , glucose: glucose_data
    , categorize_uam_as_basal: categorize_uam_as_basal
    };

    var prepped_glucose = generate(inputs);
    console.log(JSON.stringify(prepped_glucose));
}

