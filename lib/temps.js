'use strict';

function filter (treatments) {

  var results = [ ];

  var state = { };
  
  function temp (ev) {
    if ('duration (min)' in ev) {
      state.duration = ev['duration (min)'].toString( );
      state.raw_duration = ev;
    }

    if ('rate' in ev) {
      state[ev.temp] = ev.rate.toString( );
      state.rate = ev['rate'];
      state.raw_rate = ev;
    }

    if ('timestamp' in state && ev.timestamp !== state.timestamp) {
      state.invalid = true;
    } else {
      state.timestamp = ev.timestamp;
    }

    if ('duration' in state && ('percent' in state || 'absolute' in state)) {
      state.eventType = 'Temp Basal';
      results.push(state);
      state = { };
    }
  }

  function step (current) {
    switch (current._type) {
      case 'TempBasalDuration':
      case 'TempBasal':
        temp(current);
        break;
      default:
        results.push(current);
        break;
    }
  }
  treatments.forEach(step);
  return results;
}

exports = module.exports = filter;
