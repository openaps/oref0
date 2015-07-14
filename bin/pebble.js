#!/usr/bin/env node

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
    basalRate = basalprofile_data[basalprofile_data.length-1].rate
    
    for (var i = 0; i < basalprofile_data.length - 1; i++) {
        if ((now >= getTime(basalprofile_data[i].minutes)) && (now < getTime(basalprofile_data[i + 1].minutes))) {
            basalRate = basalprofile_data[i].rate;
            break;
        }
    }
}



if (!module.parent) {
    
    var glucose_input = process.argv.slice(2, 3).pop()
    var clock_input = process.argv.slice(3, 4).pop()
    var iob_input = process.argv.slice(4, 5).pop()
    var basalprofile_input = process.argv.slice(5, 6).pop()
    var currenttemp_input = process.argv.slice(6, 7).pop()
    
    if (!glucose_input || !clock_input || !iob_input || !basalprofile_input || !currenttemp_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<glucose.json> <clock.json> <iob.json> <current_basal_profile.json> <currenttemp.json>');
        process.exit(1);
    }
    
    var cwd = process.cwd()
    var glucose_data = require(cwd + '/' + glucose_input);
    var cgmtime = glucose_data[0].display_time.split("T")[1];
    var bgnow = glucose_data[0].glucose;
    var delta = bgnow - glucose_data[1].glucose;
    var tick;
    if (delta < 0) { tick = delta; } else { tick = "+" + delta; }
    var clock_data = require(cwd + '/' + clock_input);
    var pumptime = clock_data.split("T")[1];
    var iob_data = require(cwd + '/' + iob_input);
    iob = iob_data.iob.toFixed(2);
    var basalprofile_data = require(cwd + '/' + basalprofile_input);
    var basalRate;
    basalLookup();
    var temp = require(cwd + '/' + currenttemp_input);
    var tempstring;
    if (temp.duration < 1) {
        tempstring = "No temp basal\n";
    } else {
        tempstring = "Temp: " + temp.rate + "U/hr for " + temp.duration + "m ";
    }


    var pebble = {        
        "content" : "" + bgnow + tick + " " + cgmtime + "\n"
        + "IOB: " + iob + "U\n"
        + "Sched: " + basalRate + "U/hr\n"
        + tempstring
        + "as of " + pumptime,
        "refresh_frequency": 1
    };

    console.log(JSON.stringify(pebble));
}
