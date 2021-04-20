#!/usr/bin/env node
'use strict';

var os = require("os");
var fs = require('fs');
var moment = require("moment");

var requireUtils = require('../lib/require-utils');
var requireWithTimestamp = requireUtils.requireWithTimestamp;
var safeLoadFile = requireUtils.safeLoadFile;

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

function mmtuneStatus (status, cwd, mmtune_input) {
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

function preferencesStatus (status, cwd ,preferences_input) {
    var preferences = requireWithTimestamp(cwd + preferences_input);
    if (preferences) {
      status.preferences = preferences;
      if (preferences.nightscout_host) { status.preferences.nightscout_host = "redacted"; }
      if (preferences.bt_mac) { status.preferences.bt_mac = "redacted"; }
      if (preferences.pushover_token) { status.preferences.pushover_token = "redacted"; }
      if (preferences.pushover_user) { status.preferences.pushover_user = "redacted"; }
      if (preferences.pump_serial) { status.preferences.pump_serial = "redacted"; }
    }
}

function uploaderStatus (status, cwd, uploader_input) {
    var uploader = JSON.parse(fs.readFileSync(cwd + uploader_input, 'utf8'));
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




var ns_status = function ns_status(argv_params) {

    var argv = require('yargs')(argv_params)
        .usage("$0 <clock.json> <iob.json> <suggested.json> <enacted.json> <battery.json> <reservoir.json> <status.json> [--uploader uploader.json] [mmtune.json] [--preferences preferences.json]")
        .option('preferences', {
            alias: 'p',
            nargs: 1,
            describe: "OpenAPS preferences file",
            default: false
        })
        .option('uploader', {
            alias: 'u',
            nargs: 1,
            describe: "Uploader battery status",
            default: false
        })
        .strict(true)
        .fail(function (msg, err, yargs) {
            if (err) {
                return console.error('Error found', err);
            }
            return console.error('Parsing of command arguments failed', msg)
            })
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
    var preferences_input = params.preferences;
    var uploader_input = params.uploader;

    if (inputs.length < 7 || inputs.length > 8) {
        argv.showHelp();
        return;
    }

    // TODO: For some reason the following line does not work (../package.json ia not found).
    //var pjson = JSON.parse(fs.readFileSync('../package.json', 'utf8'));
    var pjson = require('../package.json');

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
            iob.mills = moment(iob.time).valueOf();
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

        if (enacted && enacted.timestamp) {
          enacted.mills = moment(enacted.timestamp).valueOf();
        }

        if (suggested && suggested.timestamp) {
          suggested.mills = moment(suggested.timestamp).valueOf();
        }

        var status = {
            device: 'openaps://' + os.hostname(),
            openaps: {
                iob: iob,
                suggested: suggested,
                enacted: enacted,
                version: pjson.version
            },
            pump: {
                clock: safeLoadFile(cwd + clock_input),
                battery: safeLoadFile(cwd + battery_input),
                reservoir: safeLoadFile(cwd + reservoir_input),
                status: requireWithTimestamp(cwd + status_input)
            },
            created_at: new Date()
        };

        if (mmtune_input) {
            mmtuneStatus(status, cwd, mmtune_input);
        }

        if (preferences_input) {
            preferencesStatus(status, cwd ,preferences_input);
        }

        if (uploader_input) {
            uploaderStatus(status, cwd, uploader_input);
        }

        return JSON.stringify(status);
    } catch (e) {
        return console.error("Could not parse input data: ", e);
    }
}

if (!module.parent) {
    // remove the first parameter.
    var command = process.argv;
    command.shift();
    command.shift();
    var result = ns_status(command);
    if(result !== undefined) {
        console.log(result);
    }
}

exports = module.exports = ns_status
