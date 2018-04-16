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

var basal = require('oref0/lib/profile/basal');
var get_iob = require('oref0/lib/iob');
var detect = require('oref0/lib/determine-basal/autosens');

if (!module.parent) {
    var detectsensitivity = init();

    var glucose_input = process.argv[2];
    var pumphistory_input = process.argv[3];
    var profile_input = process.argv[4];

    if (!glucose_input || !pumphistory_input || !profile_input) {
        console.error('usage: ', process.argv.slice(0, 2), '<glucose.json> <pumphistory.json> <profile.json>');
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

        if (typeof(profile.isfProfile == "undefined")) {
            //console.error(profile[0].store.Default.basal);
            profile =
            {
                "min_5m_carbimpact": 8,
                "dia": profile[0].store.Default.dia,
                "basalprofile": profile[0].store.Default.basal.map(convertBasal),
                "isfProfile": {
                    "units": profile[0].store.Default.units,
                    "sensitivities": [
                    {
                        "i": 0,
                        "start": profile[0].store.Default.sens[0].time + ":00",
                        "sensitivity": profile[0].store.Default.sens[0].value,
                        "offset": 0,
                        "x": 0,
                        "endOffset": 1440
                    }
                    ]
                },
                "carb_ratio": profile[0].store.Default.carbratio[0].value,
                "autosens_max": 2.0,
                "autosens_min": 0.5
            };
          //console.error(profile);
        }
        var isf_data = profile.isfProfile;
        if (typeof(isf_data) != "undefined" && typeof(isf_data.units == "string")) {
            if (isf_data.units !== 'mg/dL') {
                if (isf_data.units == 'mg/dl') {
                    isf_data.units = 'mg/dL';
                    profile.isfProfile.units = 'mg/dL';
                } else if (isf_data.units == 'mmol/L') {
                    for (var i = 0, len = isf_data.sensitivities.length; i < len; i++) {
                        isf_data.sensitivities[i].sensitivity = isf_data.sensitivities[i].sensitivity * 18;
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
        detect(detection_inputs);
        for(var i=0; i<10; i++) {
            detection_inputs.glucose_data.shift();
        }
        console.error(ratio, newisf);
        ratioArray.unshift(ratio);
    }
    while(detection_inputs.glucose_data.length > 96);
    //var lowestRatio = Math.min(ratio8h, ratio24h);
    //var sensAdj = {
        //"ratio": lowestRatio
    //}
    return console.log(JSON.stringify(ratioArray));

}

function init() {

    var detectsensitivity = {
        name: 'detect-sensitivity'
        , label: "OpenAPS Detect Sensitivity"
    };

    //detectsensitivity.getLastGlucose = require('../lib/glucose-get-last');
    //detectsensitivity.detect_sensitivity = require('../lib/determine-basal/determine-basal');
    return detectsensitivity;

}
module.exports = init;


function convertBasal(item)
{
    var convertedBasal = {
      "start": item.time + ":00",
      "minutes": Math.round(item.timeAsSeconds / 60),
      "rate": item.value
  };
  return convertedBasal;
}

// From https://gist.github.com/IceCreamYou/6ffa1b18c4c8f6aeaad2
// Returns the value at a given percentile in a sorted numeric array.
// "Linear interpolation between closest ranks" method
function percentile(arr, p) {
    if (arr.length === 0) return 0;
    if (typeof p !== 'number') throw new TypeError('p must be a number');
    if (p <= 0) return arr[0];
    if (p >= 1) return arr[arr.length - 1];

    var index = arr.length * p,
        lower = Math.floor(index),
        upper = lower + 1,
        weight = index % 1;

    if (upper >= arr.length) return arr[lower];
    return arr[lower] * (1 - weight) + arr[upper] * weight;
}

// Returns the percentile of the given value in a sorted numeric array.
function percentRank(arr, v) {
    if (typeof v !== 'number') throw new TypeError('v must be a number');
    for (var i = 0, l = arr.length; i < l; i++) {
        if (v <= arr[i]) {
            while (i < l && v === arr[i]) i++;
            if (i === 0) return 0;
            if (v !== arr[i-1]) {
                i += (v - arr[i-1]) / (arr[i] - arr[i-1]);
            }
            return i / l;
        }
    }
    return 1;
}

