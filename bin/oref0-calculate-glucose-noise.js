#!/usr/bin/env node

/*
  Glucose noise calculation

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

var generate = require('../lib/calc-glucose-stats').updateGlucoseStats;

function usage ( ) {
    console.log('usage: ', process.argv.slice(0, 2), '<glucose.json>');
}

if (!module.parent) {
  var argv = require('yargs')
    .usage("$0 <glucose.json>")
    .strict(true)
    .help('help');

  var params = argv.argv;
  var inputs = params._

  if (inputs.length !== 1) {
    argv.showHelp()
    console.error('Incorrect number of arguments');
    process.exit(1);
  }

  var glucose_input = inputs[0];

  var cwd = process.cwd();
  var glucose_hist = require(cwd + '/' + glucose_input);

  inputs = {
    glucose_hist: glucose_hist
  };

  glucose_hist = generate(inputs);
  console.log(JSON.stringify(glucose_hist));
}

