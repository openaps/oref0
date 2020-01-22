#!/usr/bin/env node

/*
  oref0 Nightscout treatment fetch tool

  Collects latest treatment data from Nightscout, with support for sending the
  If-Modified-Since header and not outputting the report file on 304 Not Modified
  response.

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

var crypto = require('crypto');
var request = require('request');
var _ = require('lodash');
var fs = require('fs');
var network = require('network');

var safe_errors = ['ECONNREFUSED', 'ESOCKETTIMEDOUT', 'ETIMEDOUT'];
var log_errors = true;

if (!module.parent) {

  var argv = require('yargs')
    .usage("$0 ns-glucose.json NSURL API-SECRET <hours>")
    .strict(true)
    .help('help');

  function usage() {
    argv.showHelp();
  }

  var params = argv.argv;
  var glucose_input = params._.slice(0, 1).pop();

  if ([null, '--help', '-h', 'help'].indexOf(glucose_input) > 0) {
    usage();
    process.exit(0);
  }

  var nsurl = params._.slice(1, 2).pop();
  if (nsurl && nsurl.charAt(nsurl.length - 1) == "/") nsurl = nsurl.substr(0, nsurl.length - 1); // remove trailing slash if it exists

  var apisecret = params._.slice(2, 3).pop();
  var hours = Number(params._.slice(3, 4).pop());
  var records = 1000;

  if (hours > 0) {
    records = 12 * hours;
  }

  if (!glucose_input || !nsurl || !apisecret) {
    usage();
    process.exit(1);
  }

  if (apisecret != null && !apisecret.startsWith("token=") && apisecret.length != 40) {
    var shasum = crypto.createHash('sha1');
    shasum.update(apisecret);
    apisecret = shasum.digest('hex');
  }

  var cwd = process.cwd();
  var outputPath = cwd + '/' + glucose_input;

  function loadFromxDrip(callback, ip) {
    var headers = {
      'api-secret': apisecret
    };

    var uri = 'http://' + ip + ':17580/sgv.json?count=' + records; // 192.168.43.1

    var options = {
      uri: uri
      , json: true
      , timeout: 10000
      , headers: headers
    };

    if (log_errors) console.error('Connected to ' + ip +', testing for xDrip API availability');

    request(options, function(error, res, data) {
      var failed = false;
      if (res && res.statusCode == 403) {
        console.error("Load from xDrip failed: API_SECRET didn't match");
        failed = true;
      }

      if (error) {
        if (safe_errors.includes(error.code)) {
          if (log_errors) console.error('Load from local xDrip timed out, likely not connected to xDrip hotspot');
          log_errors = false;
        } else {
          if (log_errors) console.error("Load from xDrip failed", error);
          log_errors = false;
          failed = true;
        }

        failed = true;
      }

      if (!failed && data) {
        console.error("CGM results loaded from xDrip");
        processAndOutput(data);
        return true;
      }

      if (failed && callback) callback();
    });

    return false;
  }

  var nsCallback = function loadFromNightscout() {
    // try Nightscout

    var lastDate;
    var glucosedata;

    fs.readFile(outputPath, 'utf8', function(err, fileContent) {

      if (err) {
        console.error(err);
      } else {
        try {
          glucosedata = JSON.parse(fileContent);

          if (glucosedata.constructor == Array) { //{ throw "Glucose data file doesn't seem to be valid"; }
            _.forEach(glucosedata, function findLatest(sgvrecord) {
              var d = new Date(sgvrecord.dateString);
              if (!lastDate || lastDate < d) {
                lastDate = d;
              }
            });
          } else {
            glucosedata = null;
          }
        } catch (e) {
          console.error(e);
        }
      }
      loadFromNightscoutWithDate(lastDate, glucosedata);
    });
  }

  function loadFromNightscoutWithDate(lastDate, glucosedata) {

    // append the token secret to the end of the ns url, or add it to the headers if token based authentication is not used
    var headers = {} ;
    var tokenAuth = "";
    if (apisecret.startsWith("token=")) {
      tokenAuth = "&" + apisecret;
    } else { 
      headers = { 'api-secret': apisecret };
    }

    if (!_.isNil(lastDate)) {
      headers["If-Modified-Since"] = lastDate.toISOString();
    }

    var uri = nsurl + '/api/v1/entries/sgv.json?count=' + records + tokenAuth;
    var options = {
      uri: uri
      , json: true
      , timeout: 90000
      , headers: headers
    };

    request(options, function(error, res, data) {
      if (res && (res.statusCode == 200 || res.statusCode == 304)) {

        if (data) {
          console.error("Got CGM results from Nightscout");
          processAndOutput(data);
        } else {
          console.error("Got Not Changed response from Nightscout, assuming no new data is available");
          // output old file
          if (!_.isNil(glucosedata)) {
            console.log(JSON.stringify(glucosedata));
          }
        }
      } else {
        console.error("Loading CGM data from Nightscout failed", error);
      }
    });

  }

  function processAndOutput(glucosedata) {

    _.forEach(glucosedata, function findLatest(sgvrecord) {
      sgvrecord.glucose = sgvrecord.sgv;
    });

    console.log(JSON.stringify(glucosedata));
  }

  network.get_gateway_ip(function(err, ip) {
    loadFromxDrip(nsCallback, ip);
  });

}
