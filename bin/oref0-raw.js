#!/usr/bin/env node
'use strict';

var fs = require('fs');
var os = require("os");

var safeRequire = require('../lib/require-utils').safeRequire;
var getLastGlucose = require('../lib/glucose-get-last');
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

function usage ( ) {
    console.error('usage: ', process.argv.slice(0, 2), '<glucose.json> <cal.json> [150]');
}
if (!module.parent) {
  var glucose_input = process.argv.slice(2, 3).pop();
  if ([null, '--help', '-h', 'help'].indexOf(glucose_input) > 0) {
    usage( );
    process.exit(0)
  }
  var cal_input = process.argv.slice(3, 4).pop();

  //limit to prevent high temping
  var max_raw = process.argv.slice(4, 5).pop();

  if (!glucose_input || !cal_input) {
    usage( );
    process.exit(1);
  }

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
