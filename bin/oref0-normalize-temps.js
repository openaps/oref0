#!/usr/bin/env node

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

var find_insulin = require('oref0/lib/temps');
var find_bolus = require('oref0/lib/bolus');
var describe_pump = require('oref0/lib/pump');
function usage ( ) {
    console.log('usage: ', process.argv.slice(0, 2), '<pumphistory.json>');
}

if (!module.parent) {
  var iob_input = process.argv[2];

  if ([null, '--help', '-h', 'help'].indexOf(iob_input) > 0) {
    usage( );
    process.exit(0)
  }
  if (!iob_input) {
    usage( )
    process.exit(1);
  }

  var cwd = process.cwd()
  try {
    var all_data = require(cwd + '/' + iob_input);
  } catch (e) {
    return console.error("Could not parse pumphistory: ", e);
  }

  var inputs = {
    history: all_data
  };
  var treatments = find_insulin(find_bolus(inputs.history));
  treatments = describe_pump(treatments);
  // treatments.sort(function (a, b) { return a.date > b.date });


  console.log(JSON.stringify(treatments));
}

