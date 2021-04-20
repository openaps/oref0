'use strict';

var getTime = require('../medtronic-clock');
var shared_node_utils = require('../../bin/oref0-shared-node-utils');
var console_error = shared_node_utils.console_error;

function bgTargetsLookup (final_result, inputs, profile) {
  return bound_target_range(lookup(final_result, inputs, profile));
}

function lookup (final_result, inputs, profile) {
    var bgtargets_data = inputs.targets;
    var temptargets_data = inputs.temptargets;
    var now = new Date();
    
    //bgtargets_data.targets.sort(function (a, b) { return a.offset > b.offset });

    var bgTargets = bgtargets_data.targets[bgtargets_data.targets.length - 1];
    
    for (var i = 0; i < bgtargets_data.targets.length - 1; i++) {
        if ((now >= getTime(bgtargets_data.targets[i].offset)) && (now < getTime(bgtargets_data.targets[i + 1].offset))) {
            bgTargets = bgtargets_data.targets[i];
            break;
        }
    }

    if (profile.target_bg) {
        bgTargets.low = profile.target_bg;
    }

    bgTargets.high = bgTargets.low;

    var tempTargets = bgTargets;

    // sort tempTargets by date so we can process most recent first
    try {
        temptargets_data.sort(function (a, b) { return new Date(b.created_at) - new Date(a.created_at) });
    } catch (e) {
        console_error(final_result, "No temptargets found.");
    }
    //console.error(temptargets_data);
    //console.error(now);
    for (i = 0; i < temptargets_data.length; i++) {
        var start = new Date(temptargets_data[i].created_at);
        //console.error(start);
        var expires = new Date(start.getTime() + temptargets_data[i].duration * 60 * 1000);
        //console.error(expires);
        if (now >= start && temptargets_data[i].duration === 0) {
            // cancel temp targets
            //console.error(temptargets_data[i]);
            tempTargets = bgTargets;
            break;
        } else if (! temptargets_data[i].targetBottom || ! temptargets_data[i].targetTop) {
            console_error(final_result, "eventualBG target range invalid: " + temptargets_data[i].targetBottom + "-" + temptargets_data[i].targetTop);
            break;
        } else if (now >= start && now < expires ) {
            //console.error(temptargets_data[i]);
            tempTargets.high = temptargets_data[i].targetTop;
            tempTargets.low = temptargets_data[i].targetBottom;
            tempTargets.temptargetSet = true;
            break;
        }
    }
    bgTargets = tempTargets;
    //console.error(bgTargets);

    return bgTargets;
}

function bound_target_range (target) {
    // if targets are < 20, assume for safety that they're intended to be mmol/L, and convert to mg/dL
    if ( target.high < 20 ) { target.high = target.high * 18; }
    if ( target.low < 20 ) { target.low = target.low * 18; }
    // hard-code lower bounds for min_bg and max_bg in case pump is set too low, or units are wrong
    target.max_bg = Math.max(80, target.high);
    target.min_bg = Math.max(80, target.low);
    // hard-code upper bound for min_bg in case pump is set too high
    target.min_bg = Math.min(200, target.min_bg);
    target.max_bg = Math.min(200, target.max_bg);
    return target
}

bgTargetsLookup.bgTargetsLookup = bgTargetsLookup;  // does use log
bgTargetsLookup.lookup = lookup; // not used outside
bgTargetsLookup.bound_target_range = bound_target_range; // does not log
exports = module.exports = bgTargetsLookup;

