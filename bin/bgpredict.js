#!/usr/bin/env node

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
    var iob_input = process.argv.slice(3, 4).pop()
    var isf_input = process.argv.slice(4, 5).pop()
    
    if (!glucose_input || !iob_input || !isf_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<glucose.json> <iob.json> <isf.json>');
        process.exit(1);
    }
    
    var cwd = process.cwd()
    var glucose_data = require(cwd + '/' + glucose_input);
    var bgnow = glucose_data[0].glucose;
    var delta = bgnow - glucose_data[1].glucose;
    var tick;
    if (delta < 0) { tick = delta; } else { tick = "+" + delta; }
    var iob_data = require(cwd + '/' + iob_input);
    iob = iob_data.iob.toFixed(2);
    var isf_data = require(cwd + '/' + isf_input);
    var isf;
    isfLookup();
    var eventualBG = Math.round( bgnow - ( iob * isf ) );

    var prediction = { "bg" : bgnow, "iob" : iob, "eventualBG" : eventualBG }

    console.log(JSON.stringify(prediction));
}
