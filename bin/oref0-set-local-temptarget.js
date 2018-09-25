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

if (!module.parent) {
    var argv = require('yargs')
      .usage('$0 <target> <duration> [<startime>]\nexample: $0 110 60\nexample: $0 120 30 2017-10-18:00:15:00.000Z')
      // error and show help if some other args given
      .strict(true)
      .help('help');

    var params = argv.argv;
    var inputs = params._;

    var target = inputs[0];
    var duration = inputs[1];
    var start = inputs[2];

    if (inputs.length < 2 || inputs.length > 3) {
        argv.showHelp();
        console.error('Incorrect number of arguments');
        process.exit(1);
    }

    var temptarget = {};
    temptarget.targetBottom = parseInt(target);
    temptarget.targetTop = parseInt(target);
    temptarget.duration = parseInt(duration);
    if (start) {
        temptarget.created_at = new Date(start);
    } else {
        temptarget.created_at = new Date();
    }

    console.log(JSON.stringify(temptarget));
}

