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
var detectSensitivity = require('../lib/determine-basal/autosens');

if (!module.parent) {
    var argv = require('yargs')
      .usage("$0 <glucose.json> <pumphistory.json> <insulin_sensitivities.json> <basal_profile.json> <profile.json> [<carbhistory.json>] [<temptargets.json>]")
      .strict(true)
      .help('help');

    var params = argv.argv;
    var inputs = params._;

    var glucose_input = inputs[0];
    var pumphistory_input = inputs[1];
    var isf_input = inputs[2];
    var basalprofile_input = inputs[3];
    var profile_input = inputs[4];
    var carb_input = inputs[5];
    var temptarget_input = inputs[6];

    if (inputs.length < 5 || inputs.length > 7) {
        argv.showHelp();
        console.error('Incorrect number of arguments');
        process.exit(1);
    }
    
    var fs = require('fs');
    try {
        var cwd = process.cwd();
        var glucose_data = require(cwd + '/' + glucose_input);
        // require 6 hours of data to run autosens
        if (glucose_data.length < 72) {
            console.error("Optional feature autosens disabled: not enough glucose data to calculate sensitivity");
            return console.log('{ "ratio": 1, "reason": "not enough glucose data to calculate autosens" }');
            //process.exit(2);
        }

        var pumphistory_data = require(cwd + '/' + pumphistory_input);
        var profile = require(cwd + '/' + profile_input);

        var isf_data = require(cwd + '/' + isf_input);
        if (isf_data.units !== 'mg/dL') {
            if (isf_data.units === 'mmol/L') {
                for (var i = 0, len = isf_data.sensitivities.length; i < len; i++) {
                    isf_data.sensitivities[i].sensitivity = isf_data.sensitivities[i].sensitivity * 18;
                }
               isf_data.units = 'mg/dL';
            } else {
                console.log('ISF is expected to be expressed in mg/dL or mmol/L.'
                        , 'Found', isf_data.units, 'in', isf_input, '.');
                process.exit(2);
            }
        }
        var basalprofile = require(cwd + '/' + basalprofile_input);

        var carb_data = { };
        if (typeof carb_input !== 'undefined') {
            try {
                carb_data = JSON.parse(fs.readFileSync(carb_input, 'utf8'));
            } catch (e) {
                console.error("Warning: could not parse "+carb_input);
            }
        }

        // TODO: add support for a proper --retrospective flag if anything besides oref0-simulator needs this
        var retrospective = false;
        var temptarget_data = { };
        if (typeof temptarget_input !== 'undefined') {
            try {
                if (temptarget_input == "retrospective") {
                    retrospective = true;
                } else {
                    temptarget_data = JSON.parse(fs.readFileSync(temptarget_input, 'utf8'));
                }
            } catch (e) {
                console.error("Warning: could not parse "+temptarget_input);
            }
        }

        var iob_inputs = {
            history: pumphistory_data
            , profile: profile
        //, clock: clock_data
        };
    } catch (e) {
        return console.error("Could not parse input data: ", e);
    }

    var detection_inputs = {
        iob_inputs: iob_inputs
        , carbs: carb_data
        , glucose_data: glucose_data
        , basalprofile: basalprofile
        , temptargets: temptarget_data
        , retrospective: retrospective
        //, clock: clock_data
    };
    console.error("Calculating sensitivity using 8h of non-exluded data");
    detection_inputs.deviations = 96;
    var result = detectSensitivity(detection_inputs);
    var ratio8h = result.ratio;
    var newisf8h = result.newisf;
    console.error("Calculating sensitivity using all non-exluded data (up to 24h)");
    detection_inputs.deviations = 288;
    result = detectSensitivity(detection_inputs);
    var ratio24h = result.ratio;
    var newisf24h = result.newisf;
    if ( ratio8h < ratio24h ) {
        console.error("Using 8h autosens ratio of",ratio8h,"(ISF",newisf8h+")");
    } else {
        console.error("Using 24h autosens ratio of",ratio24h,"(ISF",newisf24h+")");
    }
    var lowestRatio = Math.min(ratio8h, ratio24h);
    var sensAdj = {
        "ratio": lowestRatio
    }
    return console.log(JSON.stringify(sensAdj));

}


