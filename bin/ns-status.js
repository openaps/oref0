#!/usr/bin/env node
'use strict';

var os = require("os");

var requireUtils = require('../lib/require-utils');
var safeRequire = requireUtils.safeRequire;
var requireWithTimestamp = requireUtils.requireWithTimestamp;

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

function mmtuneStatus (status) {
    var mmtune = requireWithTimestamp(cwd + mmtune_input);
    if (mmtune) {
        if (mmtune.scanDetails && mmtune.scanDetails.length) {
            mmtune.scanDetails = mmtune.scanDetails.filter(function (d) {
                return d[2] > -99;
            });
        }
      status.mmtune = mmtune;
    }
}

function uploaderStatus (status) {
    var uploader = require(cwd + uploader_input);
    if (uploader) {
        if (typeof uploader === 'number') {
            status.uploader = {
                battery: uploader
            };
        } else {
            status.uploader = uploader;
        }
    }
}

if (!module.parent) {

    var argv = require('yargs')
        .usage("$0 <clock.json> <iob.json> <suggested.json> <enacted.json> <battery.json> <reservoir.json> <status.json> [--uploader uploader.json] [mmtune.json]")
        .option('uploader', {
            alias: 'u',
            nargs: 1,
            describe: "Uploader battery status",
            default: false
        })
        .strict(true)
        .help('help');

    var params = argv.argv;
    var inputs = params._;
    var clock_input = inputs[0];
    var iob_input = inputs[1];
    var suggested_input = inputs[2];
    var enacted_input = inputs[3];
    var battery_input = inputs[4];
    var reservoir_input = inputs[5];
    var status_input = inputs[6];
    var mmtune_input = inputs[7];
    var uploader_input = params.uploader;

    if (inputs.length < 7 || inputs.length > 8) {
        argv.showHelp();
        process.exit(1);
    }

    var cwd = process.cwd() + '/';

    var hostname = 'unknown';
    try {
        hostname = os.hostname();
    } catch (e) {
      return console.error('Unable to get hostname to send with status', e);
    }

    try {
        var iob = null;
        var iobArray = requireWithTimestamp(cwd + iob_input);
        var suggested = requireWithTimestamp(cwd + suggested_input);
        var enacted = requireWithTimestamp(cwd + enacted_input);

        if (iobArray && iobArray.length) {
            iob = iobArray[0];
            iob.timestamp = iob.time;
            delete iob.time;
        }

        // we only need the most current predBGs
        if (enacted && suggested) {
          if (enacted.timestamp > suggested.timestamp) {
            delete suggested.predBGs;
          } else {
            delete enacted.predBGs;
          }
        }

        var status = {
            device: 'openaps://' + os.hostname(),
            openaps: {
                iob: iob,
                suggested: suggested,
                enacted: enacted
            },
            pump: {
                clock: safeRequire(cwd + clock_input),
                battery: safeRequire(cwd + battery_input),
                reservoir: safeRequire(cwd + reservoir_input),
                status: requireWithTimestamp(cwd + status_input)
            }
        };

        if (mmtune_input) {
            mmtuneStatus(status);
        }

        if (uploader_input) {
            uploaderStatus(status);
        }

        console.log(JSON.stringify(status));
    } catch (e) {
        return console.error("Could not parse input data: ", e);
    }
}
