#!/usr/bin/env node
'use strict';

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

var basal = require('../lib/profile/basal');
var detectSensitivity = require('../lib/determine-basal/autosens');

if (!module.parent) {
    //var detectsensitivity = init(); // I don't see where this variable is used, so deleted it.

    var argv = require('yargs')
        .usage("$0 <glucose.json> <pumphistory.json> <profile.json> <readings_per_run> [outputfile.json]")
        .strict(true)
        .help('help');

    var params = argv.argv;
    var inputs = params._;

    if (inputs.length < 4 || inputs.length > 5) {
        argv.showHelp();
        process.exit(1);
    }

    var glucose_input = inputs[0];
    var pumphistory_input = inputs[1];
    var profile_input = inputs[2];
    var readings_per_run = inputs[3];
    var output_file;
    if (inputs.length === 5) {
        output_file = inputs[4];
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


        if (typeof profile.isfProfile === "undefined") {
            for (var prop in profile[0].store) {
                var profilename = prop;
            }
            //console.error(profilename);
            //console.error(profile[0].store[profilename].basal);
            //namedprofile = profile[0].store[profilename];
            //console.error(profilename, namedprofile);
            profile =
            {
                "min_5m_carbimpact": 8,
                "dia": profile[0].store[profilename].dia,
                "basalprofile": profile[0].store[profilename].basal.map(convertBasal),
                "sens": profile[0].store[profilename].sens[0].value,
                "isfProfile": {
                    "units": profile[0].store[profilename].units,
                    "sensitivities": [
                    {
                        "i": 0,
                        "start": profile[0].store[profilename].sens[0].time + ":00",
                        "sensitivity": profile[0].store[profilename].sens[0].value,
                        "offset": 0,
                        "x": 0,
                        "endOffset": 1440
                    }
                    ]
                },
                "carb_ratio": profile[0].store[profilename].carbratio[0].value,
                "autosens_max": 2.0,
                "autosens_min": 0.5
            };
            inputs = { "basals": profile.basalprofile };
            profile.max_daily_basal = basal.maxDailyBasal(inputs);
          //console.error(profile);
        }
        var isf_data = profile.isfProfile;
        if (typeof isf_data !== "undefined" && typeof isf_data.units === "string") {
            if (isf_data.units !== 'mg/dL') {
                if (isf_data.units === 'mg/dl') {
                    isf_data.units = 'mg/dL';
                    profile.isfProfile.units = 'mg/dL';
                } else if (isf_data.units === 'mmol' || isf_data.units === 'mmol/L') {
                    for (var i = 0, len = isf_data.sensitivities.length; i < len; i++) {
                        isf_data.sensitivities[i].sensitivity = isf_data.sensitivities[i].sensitivity * 18;
                        profile.sens = profile.sens * 18;
                    }
                    isf_data.units = 'mg/dL';
                } else {
                    console.log('ISF is expected to be expressed in mg/dL or mmol/L.'
                            , 'Found', isf_data.units, '.');
                    process.exit(2);
                }
            }
        } else {
            console.error("Unable to determine units.");
        }
        var basalprofile = profile.basalprofile;

        var iob_inputs = {
            history: pumphistory_data
            , profile: profile
        };
    } catch (e) {
        return console.error("Could not parse input data: ", e);
    }

    var detection_inputs = {
        iob_inputs: iob_inputs
        , carbs: {}
        , glucose_data: glucose_data
        , basalprofile: basalprofile
        , temptargets: {}
        , retrospective: true
    };
    var ratioArray = [];
    do {
        detection_inputs.deviations = 96;
        var result = detectSensitivity(detection_inputs);
        for(i=0; i<readings_per_run; i++) {
            detection_inputs.glucose_data.shift();
        }
        console.error(result.ratio, result.newisf, detection_inputs.glucose_data[0].dateString);

        var obj = {
            "dateString": detection_inputs.glucose_data[0].dateString,
            "sensitivityRatio": result.ratio,
            "ISF": result.newisf
        }
        ratioArray.unshift(obj);
        if (output_file) {
            //console.error(output_file);
            fs.writeFileSync(output_file, JSON.stringify(ratioArray)+"\n");
        } else {
            console.error(JSON.stringify(ratioArray));
        }
    }
    while(detection_inputs.glucose_data.length > 96);
    return console.log(JSON.stringify(ratioArray));

}

function init() {

    return /* detectsensitivity */ {
        name: 'detect-sensitivity'
        , label: "OpenAPS Detect Sensitivity"
    };
}
module.exports = init;


function convertBasal(item)
{
    var start = item.time.split(":")
    return {
      "start": item.time + ":00",
      "minutes": parseInt(start[0])*60 + parseInt(start[1]),
      //"minutes": Math.round(item.timeAsSeconds / 60),
      "rate": item.value
  };
}