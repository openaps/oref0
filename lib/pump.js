
function translate (treatments) {

  var results = [ ];
  
  function step (current, index) {
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
      case 'BGCapture':
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
