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

var find_insulin = require('oref0/lib/iob/history');
function usage ( ) {
    console.log('usage: ', process.argv.slice(0, 2), '<pumphistory.json> <profile.json>');
}

if (!module.parent) {
  var iob_input = process.argv[2]
  if ([null, '--help', '-h', 'help'].indexOf(iob_input) > 0) {
    usage( );
    process.exit(0)
  }
  var profile_input = process.argv[3]
  var clock_input = process.argv[4]

  if (!iob_input || !profile_input) {
    usage( );
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

