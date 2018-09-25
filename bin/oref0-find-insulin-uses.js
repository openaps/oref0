#!/usr/bin/env node

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

var find_insulin = require('../lib/iob/history');

if (!module.parent) {
  var argv = require('yargs')
    .usage('$0 <pumphistory.json> <profile.json>')
    .demand(2)
    .strict(true)
    .help('help');

  var params = argv.argv;
  var inputs = params._;

  var iob_input = inputs[0];
  var profile_input = inputs[1];

  if (inputs.length > 2) {
    argv.showHelp();
    console.error("Too many arguments");
    process.exit(1);
  }

  var cwd = process.cwd();
  var all_data = require(cwd + '/' + iob_input);
  var profile_data = require(cwd + '/' + profile_input);

  var inputs = {
    history: all_data
  , profile: profile_data
  };

  var treatments = find_insulin(inputs);

  console.log(JSON.stringify(treatments));
}

