
function translate (treatments) {

  var results = [ ];
  
  function step (current, index) {
    var invalid = false;
    switch (current._type) {
      case 'CalBGForPH':
        current.eventType = '<none>';
        current.glucose = current.amount;
        current.glucoseType = 'Finger';
        current.notes = "Pump received finger stick.";
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
