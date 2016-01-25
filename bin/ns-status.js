#!/usr/bin/env node

var fs = require('fs');
var os = require("os");

/*
  Prepare Status info to for upload to Nightscout

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

function requireWithTimestamp (path) {
  var resolved = require(path);

  if (resolved) {
    resolved.timestamp = fs.statSync(path).mtime;
  }

  return resolved;
}

if (!module.parent) {
    
    var clock_input = process.argv.slice(2, 3).pop();
    var iob_input = process.argv.slice(3, 4).pop();
    var suggested_input = process.argv.slice(4, 5).pop();
    var enacted_input = process.argv.slice(5, 6).pop();
    var battery_input = process.argv.slice(6, 7).pop();
    var reservoir_input = process.argv.slice(7, 8).pop();
    var status_input = process.argv.slice(8, 9).pop();

    if (!clock_input || !iob_input || !suggested_input || !enacted_input || !battery_input || !reservoir_input || !status_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<clock.json> <iob.json> <suggested.json> <enacted.json> <battery.json> <reservoir.json> <status.json>');
        process.exit(1);
    }

    var cwd = process.cwd();

    var hostname = 'unknown';
    try {
        hostname = os.hostname();
    } catch (e) {
      return console.error('Unable to get hostname to send with status', e);
    }

    try {
        var status = {
            device: 'openaps://' + os.hostname()
            , openaps: {
                iob: requireWithTimestamp(cwd + '/' + iob_input)
                , suggested: requireWithTimestamp(cwd + '/' + suggested_input)
                , enacted: requireWithTimestamp(cwd + '/' + enacted_input)
            }
            , pump: {
                clock: require(cwd + '/' + clock_input)
                , battery: require(cwd + '/' + battery_input)
                , reservoir: require(cwd + '/' + reservoir_input)
                , status: requireWithTimestamp(cwd + '/' + status_input)
            }
        };
    } catch (e) {
        return console.error("Could not parse input data: ", e);
    }

    console.log(JSON.stringify(status));
}
