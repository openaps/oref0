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
            console.log('Error: not enough glucose data to calculate autosens.');
            process.exit(2);
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
