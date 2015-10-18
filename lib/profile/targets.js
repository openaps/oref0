
var getTime = require('../medtronic-clock');

function bgTargetsLookup (inputs) {
  return bound_target_range(lookup(inputs));
}

function lookup (inputs) {
    var bgtargets_data = inputs.targets;
    var now = new Date();
    
    //bgtargets_data.targets.sort(function (a, b) { return a.offset > b.offset });

    var bgTargets = bgtargets_data.targets[bgtargets_data.targets.length - 1]
    
    for (var i = 0; i < bgtargets_data.targets.length - 1; i++) {
        if ((now >= getTime(bgtargets_data.targets[i].offset)) && (now < getTime(bgtargets_data.targets[i + 1].offset))) {
            bgTargets = bgtargets_data.targets[i];
            break;
        }
    }

    return bgTargets;
}

function bound_target_range (target) {
    // hard-code lower bounds for min_bg and max_bg in case pump is set too low, or units are wrong
    target.max_bg = Math.max(100, target.high);
    target.min_bg = Math.max(90, target.low);
    // hard-code upper bound for min_bg in case pump is set too high
    target.min_bg = Math.min(200, target.min_bg);
    return target
}

bgTargetsLookup.bgTargetsLookup = bgTargetsLookup;
bgTargetsLookup.lookup = lookup;
bgTargetsLookup.bound_target_range = bound_target_range;
exports = module.exports = bgTargetsLookup;

