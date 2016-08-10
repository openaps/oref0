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
var detect = require('oref0/lib/determine-basal/cob-autosens');

if (!module.parent) {
    var detectsensitivity = init();

    var glucose_input = process.argv.slice(2, 3).pop();
    var pumphistory_input = process.argv.slice(3, 4).pop();
    var isf_input = process.argv.slice(4, 5).pop()
    var basalprofile_input = process.argv.slice(5, 6).pop()
    var profile_input = process.argv.slice(6, 7).pop();

    if (!glucose_input || !pumphistory_input || !profile_input) {
        console.error('usage: ', process.argv.slice(0, 2), '<glucose.json> <pumphistory.json> <insulin_sensitivities.json> <basal_profile.json> <profile.json>');
        process.exit(1);
    }
    
    var fs = require('fs');
    try {
        var cwd = process.cwd();
        var glucose_data = require(cwd + '/' + glucose_input);
        if (glucose_data.length < 72) {
            console.error("Optional feature autosens disabled: not enough glucose data to calculate sensitivity");
            return console.log('{ "ratio": 1, "reason": "not enough glucose data to calculate autosens" }');
            //process.exit(2);
        }

        var pumphistory_data = require(cwd + '/' + pumphistory_input);
        var profile = require(cwd + '/' + profile_input);
        //console.log(profile);
        //var glucose_status = detectsensitivity.getLastGlucose(glucose_data);
        var isf_data = require(cwd + '/' + isf_input);
        if (isf_data.units !== 'mg/dL') {
            console.log('ISF is expected to be expressed in mg/dL.'
                    , 'Found', isf_data.units, 'in', isf_input, '.');
            process.exit(2);
        }
        var basalprofile = require(cwd + '/' + basalprofile_input);

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
    , glucose_data: glucose_data
    , basalprofile: basalprofile
    //, clock: clock_data
    };
    detect(detection_inputs);
    var sensAdj = {
        "ratio": ratio
    }
    return console.log(JSON.stringify(sensAdj));

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

