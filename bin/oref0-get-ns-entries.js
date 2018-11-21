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

if (!module.parent) {

    var argv = require('yargs')
        .usage("$0 ns-glucose.json NSURL API-SECRET <hours>")
        .strict(true)
        .help('help');

    function usage() {
        argv.showHelp();
    }

    var params = argv.argv;
    var errors = [];
    var warnings = [];

    var glucose_input = params._.slice(0, 1).pop();

    if ([null, '--help', '-h', 'help'].indexOf(glucose_input) > 0) {
        usage();
        process.exit(0);
    }

    var nsurl = params._.slice(1, 2).pop();
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

    if (apisecret.length != 40) {
        var shasum = crypto.createHash('sha1');
        shasum.update(apisecret);
        apisecret = shasum.digest('hex');
    }

    var lastDate = null;

    var cwd = process.cwd();
    var outputPath = cwd + '/' + glucose_input;

    /*
    function loadFromSpike () {
    
    // try xDrip
    
    var options = {
        uri: 'http://192.168.43.1:1979/api/v1/entries/sgv.json?count=576'
        , json: true
        , timeout: 10000
    };

    request(options, function(error, res, data) {
    	if (data) {
			console.error("CGM results from Nightscout written to ", outputPath);
	        var fs = require('fs');
			fs.writeFileSync(outputPath, JSON.stringify(data));
		} else {
			console.error("Load from Spike failed, exiting");
		}
	 	process.exit(1);
    });
    
    }
    */

    function loadFromxDrip(callback,ip) {

        // try xDrip

        var headers = {
            'api-secret': apisecret
        };

        var uri = 'http://' + ip + ':17580/sgv.json?count=' + records; _// 192.168.43.1

        var options = {
            uri: uri,
            json: true,
            timeout: 10000,
            headers: headers
        };

        console.error("Trying to load CGM data from local xDrip");

        request(options, function(error, res, data) {
            if (data) {
                console.error("CGM results loaded from xDrip");
                processAndOutput(data);
                return true;
                //	        var fs = require('fs');
                //			fs.writeFileSync(outputPath, JSON.stringify(data));
            } else {
                if (error.code == 'ETIMEDOUT') {
                    console.error('Load from xDrip timed out');
                }
                else
                {
                    console.error("Load from xDrip failed", error);
                }
                if (callback) callback();
            }
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
                            if (!lastDate ||  lastDate < d) {
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

        var headers = {
            'api-secret': apisecret
        };

        if (!_.isNil(lastDate)) {
            headers["If-Modified-Since"] = lastDate.toISOString();
        }

        var uri = nsurl + '/api/v1/entries/sgv.json?count=' + records;
        var options = {
            uri: uri,
            json: true,
            headers: headers
        };

        // console.error(headers);

        request(options, function(error, res, data) {
            //console.error(res);

            if (res && (res.statusCode == 200 ||  res.statusCode == 304)) {

                if (data) {
                    console.error("Got CGM results from Nightscout");
                    processAndOutput(data);
                    //	        var fs = require('fs');
                    //			fs.writeFileSync(outputPath, JSON.stringify(data));
                } else {
                    console.error("Got Not Changed response from Nightscout, assuming no new data is available");
                    // output old file

                    if (!_.isNil(glucosedata)) {
                        console.log(glucosedata);
                    }

                }
            } else {
                console.error("Load from Nightscout failed", error);
                //loadFromxDrip ();
            }

            //process.exit(1);
        });

    }

    function processAndOutput(glucosedata) {

        _.forEach(glucosedata, function findLatest(sgvrecord) {
            sgvrecord.glucose = sgvrecord.sgv;
        });

        console.log(JSON.stringify(glucosedata));

    }

    network.get_gateway_ip(function(err, ip) {
        console.error("My router IP is " + ip); // err may be 'No active network interface found.'
        loadFromxDrip(nsCallback, ip);
      });

    //loadFromxDrip(nsCallback);
    // loadFromNightscout();

}