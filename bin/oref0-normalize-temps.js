#!/usr/bin/env node
'use strict';

/*
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

var find_insulin = require('../lib/temps');
var find_bolus = require('../lib/bolus');
var describe_pump = require('../lib/pump');
var fs = require('fs');


  
var oref0_normalize_temps = function oref0_normalize_temps(argv_params) {  
  var argv = require('yargs')(argv_params)
    .usage('$0 <pumphistory.json>')
    .demand(1)
    // error and show help if some other args given
    .strict(true)
    .help('help');

  var params = argv.argv;
  var iob_input = params._[0];

  if (params._.length > 1) {
    argv.showHelp();
    return console.error('Too many arguments');
  }

  var cwd = process.cwd()
  try {
    var all_data = JSON.parse(fs.readFileSync(cwd + '/' + iob_input));
  } catch (e) {
    return console.error("Could not parse pumphistory: ", e);
  }

  var inputs = {
    history: all_data
  };
  var treatments = find_insulin(find_bolus(inputs.history));
  treatments = describe_pump(treatments);
  // treatments.sort(function (a, b) { return a.date > b.date });


  return JSON.stringify(treatments);
}

if (!module.parent) {
   // remove the first parameter.
   var command = process.argv;
   command.shift();
   command.shift();
   var result = oref0_normalize_temps(command)
   if(result !== undefined) {
       console.log(result);
   }
}

exports = module.exports = oref0_normalize_temps
