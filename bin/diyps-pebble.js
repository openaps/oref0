#!/usr/bin/env node

/*
  Update Pebble Watch information

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

function getTime(minutes) {
    var baseTime = new Date();
    baseTime.setHours('00');
    baseTime.setMinutes('00');
    baseTime.setSeconds('00');    
    
    return baseTime.getTime() + minutes * 60 * 1000;
   
}

/* Return basal rate(U / hr) at the provided timeOfDay */

function basalLookup() {
    var now = new Date();
    basalRate = Math.round(basalprofile_data[basalprofile_data.length-1].rate*100)/100
    
    for (var i = 0; i < basalprofile_data.length - 1; i++) {
        if ((now >= getTime(basalprofile_data[i].minutes)) && (now < getTime(basalprofile_data[i + 1].minutes))) {
            basalRate = basalprofile_data[i].rate.toFixed(2);
            break;
        }
    }
}



function fileHM(file) {
    var filedate = new Date(fs.statSync(file).mtime);
    var HMS = filedate.toLocaleTimeString().split(":")
    return HMS[0].concat(":", HMS[1]);
}

if (!module.parent) {
    
    var fs = require('fs');

    var glucose_input = process.argv.slice(2, 3).pop()
    var iob_input = process.argv.slice(3, 4).pop()
    var basalprofile_input = process.argv.slice(4, 5).pop()
    var currenttemp_input = process.argv.slice(5, 6).pop()
    var requestedtemp_input = process.argv.slice(6, 7).pop()
    var enactedtemp_input = process.argv.slice(7, 8).pop()
    
    if (!glucose_input || !iob_input || !basalprofile_input || !currenttemp_input || !requestedtemp_input || !enactedtemp_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<glucose.json> <iob.json> <current_basal_profile.json> <currenttemp.json> <requestedtemp.json> <enactedtemp.json>');
        process.exit(1);
    }
    
    var cwd = process.cwd()
    var file = cwd + '/' + glucose_input;
    var glucose_data = require(file);
    var bgTime = fileHM(file);
    if (glucose_data[0].dateString) {
        var bgDate = new Date(glucose_data[0].dateString);
        var HMS = bgDate.toLocaleTimeString().split(":")
        bgTime = HMS[0].concat(":", HMS[1]);
    }

    var bgnow = glucose_data[0].glucose;
    var iob_data = require(cwd + '/' + iob_input);
    iob = iob_data.iob.toFixed(1);
    var basalprofile_data = require(cwd + '/' + basalprofile_input);
    var basalRate;
    basalLookup();
    file = cwd + '/' + currenttemp_input;
    var temp = require(file);
    var temp_time = fileHM(file);
    var tempstring;
    if (temp.duration < 1) {
        tempstring = "No temp basal";
    } else {
        tempstring = "Tmp: " + temp.duration + "m@" + temp.rate.toFixed(1);
    }
    var requestedtemp = require(cwd + '/' + requestedtemp_input);
    var reqtempstring;
    if (typeof requestedtemp.duration === 'undefined') {
        reqtempstring = "None";
    }
    else if (requestedtemp.duration < 1) {
        reqtempstring = "Cancel";
    } else { 
        reqtempstring = requestedtemp.duration + "m@" + requestedtemp.rate.toFixed(1) + "U";
    }
    var enactedtemp = require(cwd + '/' + enactedtemp_input);
    if (enactedtemp.duration < 1) {
        enactedstring = "Cancel";
    } else { 
        enactedstring = enactedtemp.duration + "m@" + enactedtemp.rate.toFixed(1) + "U";
    }
    tz = new Date().toString().match(/([-\+][0-9]+)\s/)[1]
    enactedDate = new Date(enactedtemp.timestamp.concat(tz));
    enactedHMS = enactedDate.toLocaleTimeString().split(":")
    enactedat = enactedHMS[0].concat(":", enactedHMS[1]);


    var pebble = {        
        "content" : "" + bgnow + requestedtemp.tick + " " + bgTime + "\n"
        + iob + "U->" + requestedtemp.eventualBG + "-" + requestedtemp.snoozeBG + "\n"
        + "Act: " + enactedstring 
        + " at " + enactedat + "\n"
        + tempstring
        + " at " + temp_time + "\n"
        + "Req: " + reqtempstring + "\n"
        + requestedtemp.reason + "\n"
        + "Sched: " + basalRate + "U/hr\n",
        "refresh_frequency": 1
    };

    console.log(JSON.stringify(pebble));
}
