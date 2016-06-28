#!/usr/bin/env node

/*
  Send Device Status to Azure for Push Notifications

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
var reason = process.argv.slice(2, 3).pop()

var data = JSON.stringify({
    "DeviceName": "Medtronics",
    "TimeStamp": new Date(),
    "Reason":  reason   }
);

var options = {
    host: 'openapsapi.azurewebsites.net',
    port: '443',
    path: '/api/devices',
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
