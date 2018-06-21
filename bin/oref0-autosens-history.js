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


function convertBasal(item)
{
    var convertedBasal = {
      "start": item.time + ":00",
      "minutes": Math.round(item.timeAsSeconds / 60),
      "rate": item.value
  };
  return convertedBasal;
}


