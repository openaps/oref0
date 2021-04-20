#!/usr/bin/env node
'use strict';
/*
  Insulin On Board (IOB) calculations.

  IOB is also known as "Bolus on Board", "Active Insulin", or "Insulin Remaining"

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

var generate = require('../lib/iob');
var fs = require('fs');
function usage ( ) {
    console.log('usage: ', process.argv.slice(0, 2), '<pumphistory-zoned.json> <profile.json> <clock-zoned.json> [autosens.json] [pumphistory-24h-zoned.json]');

}



var oref0_calculate_iob = function oref0_calculate_iob(argv_params) {  
  var argv = require('yargs')(argv_params)
    .usage("$0 <pumphistory-zoned.json> <profile.json> <clock-zoned.json> [<autosens.json>] [<pumphistory-24h-zoned.json>]")
    .strict(true)
    .help('help');

  var params = argv.argv;
  var inputs = params._

  if (inputs.length < 3 || inputs.length > 5) {
    argv.showHelp()
    console.error('Incorrect number of arguments');
    process.exit(1);
  }

  var pumphistory_input = inputs[0];
  var profile_input = inputs[1];
  var clock_input = inputs[2];
  var autosens_input = inputs[3];
  var pumphistory_24_input = inputs[4];

  var cwd = process.cwd();
  var pumphistory_data = JSON.parse(fs.readFileSync(cwd + '/' + pumphistory_input));
  var profile_data = JSON.parse(fs.readFileSync(cwd + '/' + profile_input));
  var clock_data = JSON.parse(fs.readFileSync(cwd + '/' + clock_input));

  var autosens_data = null;
  if (autosens_input) {
    try {
        autosens_data = JSON.parse(fs.readFileSync(cwd + '/' + autosens_input));
    } catch (e) {}
    //console.error(autosens_input, JSON.stringify(autosens_data));
  }
  var pumphistory_24_data = null;
  if (pumphistory_24_input) {
    try {
        pumphistory_24_data = JSON.parse(fs.readFileSync(cwd + '/' + pumphistory_24_input));
    } catch (e) {}
  }

  // pumphistory_data.sort(function (a, b) { return a.date > b.date });

  inputs = {
    history: pumphistory_data
  , history24: pumphistory_24_data
  , profile: profile_data
  , clock: clock_data
  };
  if ( autosens_data ) {
    inputs.autosens = autosens_data;
  }

  var iob = generate(inputs);
  return(JSON.stringify(iob));
}

if (!module.parent) {
   // remove the first parameter.
   var command = process.argv;
   command.shift();
   command.shift();
   var result = oref0_calculate_iob(command)
   console.log(result);
}

exports = module.exports = oref0_calculate_iob