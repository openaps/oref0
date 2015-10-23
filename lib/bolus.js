
function reduce (treatments) {

  var results = [ ];

  var state = { };
  var previous = [ ];
  
  function in_previous (ev) {
    var found = false;
    previous.forEach(function (elem) {
      if (elem.timestamp == ev.timestamp && ev._type == elem._type) {
        found = true;
      }
    });

    return found;
  }

  function within_minutes_from (origin, tail, minutes) {
    var ms = minutes * 1000 * 60;
    var ts = Date.parse(origin.timestamp);
    var candidates = tail.slice( ).filter(function (elem) {
      var dt = Date.parse(origin.timestamp);
      return ts - dt <= ms;
      
    });
    return candidates;
  }

  function bolus (ev, remaining) {
    if (!ev) { return; }
    if (ev._type == 'BolusWizard') {
      state.carbs = ev.carb_input;
      state.ratio = ev.carb_ratio;
      state.bg = ev.bg;
      state.wizard = ev;
      state.created_at = state.timestamp = ev.timestamp;
      previous.push(ev);
    }

    if (ev._type == 'Bolus') {
      state.duration = ev.duration;
      state.insulin = ev.amount;
      state.bolus = ev;
      state.created_at = state.timestamp = ev.timestamp;
      previous.push(ev);
    }


    if (remaining && remaining.length > 0) {
      return bolus(remaining[0], remaining.slice(1));
    } else {
      state.eventType = '<none>';

      var has_insulin = state.insulin && state.insulin > 0;
      var has_carbs = state.carbs && state.carbs > 0;
      var has_wizard = state.wizard ? true : false;
      var has_bolus = state.bolus ? true : false;
      if (state.carbs && state.insulin && state.bg) {
        state.eventType = 'Meal Bolus';
      } else {
        if (has_carbs && !has_insulin) {
          state.eventType = 'Carb Correction';
        }
        if (!has_carbs && has_insulin) {
          state.eventType = 'Correction Bolus';
        }
      }
      results.push(state);
      state = { };
    }
  }

  function step (current, index) {
    if (in_previous(current)) {
      return;
    }
    switch (current._type) {
      case 'Bolus':
      case 'BolusWizard':
        var tail = within_minutes_from(current, treatments.slice(index+1), 4);
        bolus(current, tail);
        break;
      default:
        results.push(current);
        break;
    }
  }
  treatments.forEach(step);
  return results;
}

exports = module.exports = reduce;
