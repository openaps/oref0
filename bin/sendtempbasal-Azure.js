#!/usr/bin/env node

/*
  Send Temporary Basal to Azure

  Copyright (c) 2015 OpenAPS Contributors

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
var http = require('https');

if (!module.parent) {
    var iob_input = process.argv.slice(2, 3).pop()
    var enacted_temps_input = process.argv.slice(3, 4).pop()
    var glucose_input = process.argv.slice(4, 5).pop()
    var webapi = process.argv.slice(5, 6).pop()
    if (!iob_input || !enacted_temps_input || !glucose_input || !webapi) {
        console.log('usage: ', process.argv.slice(0, 2), '<iob.json> <enactedBasal.json> <bgreading.json> <[your_webapi].azurewebsites.net>');
        process.exit(1);
    }
}

var cwd = process.cwd();
var glucose_data = require(cwd + '/' + glucose_input);
var enacted_temps = require(cwd + '/' + enacted_temps_input);
var iob_data = require(cwd + '/' + iob_input);



var data = JSON.stringify({
    "Id": 3,
    "temp": enacted_temps.temp,
    "rate": enacted_temps.rate,
    "duration": enacted_temps.duration,
    "bg": glucose_data[0].glucose,
    "iob": iob_data.iob,
    "timestamp": enacted_temps.timestamp,
    "received": enacted_temps.recieved
}
);

var options = {
    host: webapi,
    port: '443',
    path: '/api/openapstempbasals',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': data.length
    }
};

var req = http.request(options, function (res) {
    var msg = '';
    
    res.setEncoding('utf8');
    res.on('data', function (chunk) {
        msg += chunk;
    });
    res.on('end', function () {
        console.log(JSON.parse(msg));
    });
});

req.write(data);
req.end();
