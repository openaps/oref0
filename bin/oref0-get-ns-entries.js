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

if (!module.parent) {

    var argv = require('yargs')
        .usage("$0 ns-glucose.json NSURL API-SECRET")
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
    
    function loadFromxDrip () {
    
    // try xDrip
    
    var headers = {'api-secret': apisecret};
    
    var options = {
        uri: 'http://192.168.43.1:17580/sgv.json?count=1000'
        , json: true
        , timeout: 10000
        , headers: headers
    };

    request(options, function(error, res, data) {
    	if (data) {
//			console.error("CGM results loaded from xDrip");
            processAndOutput(data);
//	        var fs = require('fs');
//			fs.writeFileSync(outputPath, JSON.stringify(data));
		} else {
//			console.error("Load from xDrip failed"); //", trying Spike");
//			loadFromSpike();
		}
		process.exit(1);
    });
    
    }
    
    function loadFromNightscout() {
    
    // try Nightscout

    var lastDate;
    var glucosedata;
        
    try {
        glucosedata = JSON.parse(fs.readFileSync(outputPath,'UTF8'));

        //var glucosedata = require(outputPath);
        
        if (glucosedata.constructor == Array) { //{ throw "Glucose data file doesn't seem to be valid"; }
            _.forEach(glucosedata,function findLatest(sgvrecord) {
                var d = new Date(sgvrecord.dateString);
                if (!lastDate || lastDate < d) {
                    lastDate = d;
                }
            });
        }
        
    } catch (e) {
        //console.error('Error parsing input', e);
    }

	var headers = {'api-secret': apisecret};
	
	if (!_.isNil(lastDate)) {
	    headers["If-Modified-Since"] = lastDate.toISOString();
	}

    var options = {
        uri: nsurl + '/api/v1/entries/sgv.json?count=1000'
        , json: true
        , headers: headers
    };
    
   // console.error(headers);

    request(options, function(error, res, data) {
        //console.error(res);
        
        if (res && (res.statusCode == 200 || res.statusCode == 304)) {
        
		if (data) {
            //console.error("fetched CGM results from Nightscout");
            processAndOutput(data);
//	        var fs = require('fs');
//			fs.writeFileSync(outputPath, JSON.stringify(data));
		} else {
//            console.error("Got Not Changed response from Nightscout, assuming no new data is available");
            // output old file

            if (!_.isNil(glucosedata)) { console.log(glucosedata); }

		}
		} else {
			//console.error("Load from Nightscout failed, trying local xDrip");
			loadFromxDrip ();
		}
		
		//process.exit(1);
    });
    
    }

    function processAndOutput(glucosedata) {

        _.forEach(glucosedata,function findLatest(sgvrecord) {
            sgvrecord.glucose = sgvrecord.sgv;
        });

        console.log(JSON.stringify(glucosedata));

    }
    
     loadFromNightscout();
    
}