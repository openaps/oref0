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
            basalRate = basalprofile_data[i].rate.toFixed(2);
            break;
        }
    }
}


function isfLookup() {
    var now = new Date();
    //isf_data.sensitivities.sort(function (a, b) { return a.offset > b.offset });
    var isfSchedule = isf_data.sensitivities[isf_data.sensitivities.length - 1]
    
    for (var i = 0; i < isf_data.sensitivities.length - 1; i++) {
        if ((now >= getTime(isf_data.sensitivities[i].offset)) && (now < getTime(isf_data.sensitivities[i + 1].offset))) {
            isfSchedule = isf_data.sensitivities[i];
            break;
        }
    }
    isf = isfSchedule.sensitivity;
}


if (!module.parent) {
    
    var glucose_input = process.argv.slice(2, 3).pop()
    var clock_input = process.argv.slice(3, 4).pop()
    var iob_input = process.argv.slice(4, 5).pop()
    var basalprofile_input = process.argv.slice(5, 6).pop()
    var currenttemp_input = process.argv.slice(6, 7).pop()
    var isf_input = process.argv.slice(7, 8).pop()
    var requestedtemp_input = process.argv.slice(8, 9).pop()
    
    if (!glucose_input || !clock_input || !iob_input || !basalprofile_input || !currenttemp_input || !isf_input || !requestedtemp_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<glucose.json> <clock.json> <iob.json> <current_basal_profile.json> <currenttemp.json> <isf.json> <requestedtemp.json>');
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
    iob = iob_data.iob.toFixed(1);
    var basalprofile_data = require(cwd + '/' + basalprofile_input);
    var basalRate;
    basalLookup();
    var temp = require(cwd + '/' + currenttemp_input);
    var tempstring;
    if (temp.duration < 1) {
        tempstring = "No temp basal";
    } else {
        tempstring = "Tmp: " + temp.duration + "m@" + temp.rate.toFixed(1);
    }
    var isf_data = require(cwd + '/' + isf_input);
    var isf;
    isfLookup();
    var eventualBG = Math.round( bgnow - ( iob * isf ) );
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


    var pebble = {        
        "content" : "" + bgnow + tick + " " + cgmtime + "\n"
        + "IOB: " + iob + "U->" + eventualBG + "\n"
        + "Sched: " + basalRate + "U/hr\n"
        + tempstring
        + " at " + pumptime + "\n"
        + "Req: " + reqtempstring,
        "refresh_frequency": 1
    };

    console.log(JSON.stringify(pebble));
}
