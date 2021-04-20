'use strict';

function translate (treatments) {

  var results = [ ];
  
  function step (current) {
    var invalid = false;
    switch (current._type) {
      case 'CalBGForPH':
        current.eventType = 'BG Check';
        current.glucose = current.amount;
        current.glucoseType = 'Finger';
        break;
      case 'BasalProfileStart':
      case 'ResultDailyTotal':
      case 'BGReceived':
      case 'Sara6E':
      case 'Model522ResultTotals':
      case 'Model722ResultTotals':
        invalid = true;
        break;
      default:
        break;
    }

    if (!invalid) {
      results.push(current);
    }

  }
  treatments.forEach(step);
  return results;
}

exports = module.exports = translate;
