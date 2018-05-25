#!/usr/bin/env node

/*
  oref0 autotuning tool

  Uses the output of oref0-autotune-prep.js

  Calculates adjustments to basal schedule, ISF, and CSF 

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

var autotune = require('oref0/lib/autotune');
var stringify = require('json-stable-stringify');
function usage ( ) {
        console.error('usage: ', process.argv.slice(0, 2), '<autotune/glucose.json> <autotune/autotune.json> <settings/profile.json>');
}

if (!module.parent) {
    var prepped_glucose_input = process.argv[2];
    if ([null, '--help', '-h', 'help'].indexOf(prepped_glucose_input) > 0) {
      usage( );
      process.exit(0)
    }
    var previous_autotune_input = process.argv[3];
    var pumpprofile_input = process.argv[4];

    if (!prepped_glucose_input || !previous_autotune_input || !pumpprofile_input ) {
        usage( );
        console.log('{ "error": "Insufficient arguments" }');
        process.exit(1);
    }

    var fs = require('fs');
    try {
        var prepped_glucose_data = JSON.parse(fs.readFileSync(prepped_glucose_input, 'utf8'));
        var previous_autotune_data = JSON.parse(fs.readFileSync(previous_autotune_input, 'utf8'));
        var pumpprofile_data = JSON.parse(fs.readFileSync(pumpprofile_input, 'utf8'));
    } catch (e) {
        console.log('{ "error": "Could not parse input data" }');
        return console.error("Could not parse input data: ", e);
    }

    var inputs = {
        preppedGlucose: prepped_glucose_data
      , previousAutotune: previous_autotune_data
      , pumpProfile: pumpprofile_data
    };

    var autotune_output = autotune(inputs);
    console.log(stringify(autotune_output, { space: '   '}));
}

