#!/usr/bin/env node
'use strict';

var safeRequire = require('../lib/require-utils').safeRequire;
var withRawGlucose = require('../lib/with-raw-glucose');

/*
 Fills CGM data doesn't already contain an EVG, if we have unfiltered, filtered, and a cal

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

if (!module.parent) {
  var argv = require('yargs')
    .usage('$0 <glucose.json> <cal.json> [<max_raw>]')
    // error and show help if some other args given
    .strict(true)
    .help('help');

  var params = argv.argv;
  var inputs = params._;

  if (inputs.length < 2 || inputs.length > 3) {
    argv.showHelp();
    console.error('Incorrect number of arguments');
    process.exit(1);
  }

  var glucose_input = inputs[0];
  var cal_input = inputs[1];

  //limit to prevent high temping
  var max_raw = inputs[2];

  try {
    var cwd = process.cwd();
    var glucose_data = safeRequire(cwd + '/' + glucose_input);
    var cals = safeRequire(cwd + '/' + cal_input);


    glucose_data = glucose_data.map(function each (entry) {
      return withRawGlucose(entry, cals, max_raw);
    });

    console.log(JSON.stringify(glucose_data));

  } catch (e) {
    return console.error("Could not parse input data: ", e);
  }

}
