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

if (!module.parent) {
  var argv = require('yargs')
    .usage("$0 pumphistory-zoned.json profile.json clock-zoned.json [--prepared]")
    .option('prepared', {
      alias: 'p',
      describe: "Pump history prepared using mmhistorytools",
      boolean: true
    })
    // error and show help if some other args given
    .strict(true)
    .help('help')
    .argv
  ;

  function usage ( ) {
    argv.showHelp( );
  }

  var pumphistory_input = argv._.slice(0, 1).pop();
  if ([null, '--help', '-h', 'help'].indexOf(pumphistory_input) > 0) {
    usage( );
    process.exit(0)
  }
  var profile_input = argv._.slice(1, 2).pop();
  var clock_input = argv._.slice(2, 3).pop();

  if (!pumphistory_input || !profile_input) {
    usage( );
    process.exit(1);
  }

  var cwd = process.cwd();
  var all_data = require(cwd + '/' + pumphistory_input);
  var profile_data = require(cwd + '/' + profile_input);
  var clock_data = require(cwd + '/' + clock_input);
  var generate = (argv.prepared) ? require('oref0/lib/iob-prepared') : require('oref0/lib/iob');

  // all_data.sort(function (a, b) { return a.date > b.date });

  var inputs = {
    history: all_data
  , profile: profile_data
  , clock: clock_data
  };

  var iob = generate(inputs);
  console.log(JSON.stringify(iob));
}
