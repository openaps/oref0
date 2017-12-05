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

var generate = require('oref0/lib/iob');
function usage ( ) {
    console.log('usage: ', process.argv.slice(0, 2), '<pumphistory-zoned.json> <profile.json> <clock-zoned.json> [autosens.json]');

}

if (!module.parent) {
  var pumphistory_input = process.argv[2];
  if ([null, '--help', '-h', 'help'].indexOf(pumphistory_input) > 0) {
    usage( );
    process.exit(0)
  }
  var profile_input = process.argv[3];
  var clock_input = process.argv[4];
  var autosens_input = process.argv[5];

  if (!pumphistory_input || !profile_input) {
    usage( );
    process.exit(1);
  }

  var cwd = process.cwd();
  var all_data = require(cwd + '/' + pumphistory_input);
  var profile_data = require(cwd + '/' + profile_input);
  var clock_data = require(cwd + '/' + clock_input);

  var autosens_data = null;
  if (autosens_input) {
    try {
        var autosens_data = require(cwd + '/' + autosens_input);
    } catch (e) {}
    //console.error(autosens_input, JSON.stringify(autosens_data));
  }

  // all_data.sort(function (a, b) { return a.date > b.date });

  var inputs = {
    history: all_data
  , profile: profile_data
  , clock: clock_data
  };
  if ( autosens_data ) {
    inputs.autosens = autosens_data;
  }

  var iob = generate(inputs);
  console.log(JSON.stringify(iob));
}

