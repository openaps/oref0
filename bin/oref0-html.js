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
    var argv = require('yargs')
        .usage('$0 <glucose.json> <iob.json> <current_basal_profile.json> <currenttemp.json> <requestedtemp.json> <enactedtemp.json> [meal.json]')
        .demand(6)
        .strict(true)
        .help('help');
    
    var fs = require('fs');

    var params = argv.argv;
    var inputs = params._;

    var glucose_input = inputs[0];
    var iob_input = inputs[1];
    var basalprofile_input = inputs[2];
    var currenttemp_input = inputs[3];
    var requestedtemp_input = inputs[4];
    var enactedtemp_input = inputs[5];
    var meal_input = inputs[6];
    
    if (inputs.length > 7) {
        argv.showHelp();
        console.error('Too many arguments');
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
    var delta = glucose_data[0].glucose - glucose_data[1].glucose;
    var tick = delta;
    if (delta >= 0) { tick = "+" + delta; } 
    var iob_data = require(cwd + '/' + iob_input);
    var iob = iob_data[0].iob.toFixed(1);
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
        tempstring = "Tmp: " + temp.duration + "m @ " + temp.rate.toFixed(1);
    }
    try {
        var requestedtemp = require(cwd + '/' + requestedtemp_input);
    } catch (e) {
        return console.error("Could not parse requestedtemp: ", e);
    }
    var reqtempstring;
    if (typeof requestedtemp.duration === 'undefined') {
        reqtempstring = "None";
    }
    else if (requestedtemp.duration < 1) {
        reqtempstring = "Cancel";
    } else { 
        reqtempstring = requestedtemp.duration + "m@" + requestedtemp.rate.toFixed(1) + "U";
    }
    //var enactedtemp = require(cwd + '/' + enactedtemp_input);
    //if (enactedtemp.duration < 1) {
        //enactedstring = "Cancel";
    //} else { 
        //enactedstring = enactedtemp.duration + "m@" + enactedtemp.rate.toFixed(1) + "U";
    //}
    var tz = new Date().toString().match(/([-+][0-9]+)\s/)[1]
    //enactedDate = new Date(enactedtemp.timestamp.concat(tz));
    //enactedHMS = enactedDate.toLocaleTimeString().split(":")
    //enactedat = enactedHMS[0].concat(":", enactedHMS[1]);

    var mealCOB = "???";
    if (typeof meal_input !== 'undefined') {
        try {
            var meal_data = JSON.parse(fs.readFileSync(meal_input, 'utf8'));
            //console.error(JSON.stringify(meal_data));
            if (typeof meal_data.mealCOB !== 'undefined') {
                mealCOB = meal_data.mealCOB;
            }
        } catch (e) {
            //console.error("Optional feature Meal Assist not configured.");
        }
    }

//console.log("<!-- ");
console.log( bgnow + requestedtemp.tick + " " + bgTime + ", "
    + iob + "U -> " + requestedtemp.eventualBG + ", "
    + tempstring + "U/hr @ " + temp_time
    + " " + reqtempstring
    + ", " + requestedtemp.reason + ", "
    //+ "Sched: " + basalRate + "U/hr, "
    //+ "mealCOB: " + mealCOB + "g"
    );
//console.log(" -->");

console.log("<body>");
    console.log("<title>");
        console.log( bgnow + " " + tick + " at " + bgTime );
    console.log("</title>");
    console.log('<meta http-equiv="refresh" content="60">');
    console.log('<meta name="viewport" content="width=500">');
console.log("<head>");

console.log("<body>");

        console.log("<h1>");
        console.log( bgnow + " " + tick + " at " + bgTime );
        console.log("<br>");
        console.log( "IOB: " + iob + "U, eventually " + requestedtemp.eventualBG + " mg/dL" );
        console.log("<br>");
        //+ "Act: " + enactedstring
        //+ " at " + enactedat + "\n"
        console.log( tempstring );
        console.log( "U/hr at " + temp_time );
        console.log("</h1>");
        console.log("<br>");
        console.log( "Req: " + reqtempstring );
        console.log("<br>");
        console.log( requestedtemp.reason );
        console.log("<br>");
        console.log( "Sched: " + basalRate + "U/hr" );
        console.log("<br>");
        console.log( "mealCOB: " + mealCOB + "g" );


console.log("</body>");


}

