'use strict';

require('should');

describe('IOB', function ( ) {

  it('should calculate IOB', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , inputs = {
        clock: timestamp
        , history: [{
        _type: 'Bolus'
        , amount: 1
        , timestamp: timestamp
        }]
        , profile: {
          dia: 3
          , bolussnooze_dia_divisor: 2
        }
      };

    var rightAfterBolus = require('../lib/iob')(inputs)[0];
    rightAfterBolus.iob.should.equal(1);
    rightAfterBolus.bolussnooze.should.equal(1);

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    hourLater.iob.should.be.lessThan(1);
    hourLater.bolussnooze.should.be.lessThan(.5);
    hourLater.iob.should.be.greaterThan(0);

    var afterDIAInputs = inputs;
    afterDIAInputs.clock = new Date(now + (3 * 60 * 60 * 1000)).toISOString();
    var afterDIA = require('../lib/iob')(afterDIAInputs)[0];

    afterDIA.iob.should.equal(0);
    afterDIA.bolussnooze.should.equal(0);
  });

  it('should snooze fast if bolussnooze_dia_divisor is high', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , inputs = {
        clock: timestamp
        , history: [{
        _type: 'Bolus'
        , amount: 1
        , timestamp: timestamp
        }]
        , profile: {
          dia: 3
          , bolussnooze_dia_divisor: 10
        }
      };

    var snoozeInputs = inputs;
    snoozeInputs.clock = new Date(now + (20 * 60 * 1000)).toISOString();
    var snooze = require('../lib/iob')(snoozeInputs)[0];
    snooze.bolussnooze.should.equal(0);
  });

  it('should calculate IOB with Temp Basals', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , timestampEarly = new Date(now - (30 * 60 * 1000)).toISOString()
      , inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly}
        , {_type: 'TempBasal', rate: 2, date: timestampEarly, timestamp: timestampEarly}
        , {_type: 'TempBasal', rate: 2, date: timestamp, timestamp: timestamp}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
        , profile: { dia: 3, current_basal: 1, bolussnooze_dia_divisor: 2}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    
    hourLater.iob.should.be.lessThan(1);
    hourLater.iob.should.be.greaterThan(0);
    
  });

  it('should calculate IOB with Temp Basal events that overlap', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , timestampEarly = new Date(now - 1).toISOString()
      , inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly}
        ,{_type: 'TempBasal', rate: 2, date: timestampEarly, timestamp: timestampEarly}
        ,{_type: 'TempBasal', rate: 2, date: timestamp, timestamp: timestamp}
		,{_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
		, profile: { dia: 3, current_basal: 1}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    
    hourLater.iob.should.be.lessThan(1);
    hourLater.iob.should.be.greaterThan(0);
    
  });

  it('should calculate IOB with Temp Basals that are lower than base rate', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , timestampEarly = new Date(now - (30 * 60 * 1000)).toISOString()
      , inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly}
        , {_type: 'TempBasal', rate: 1, date: timestampEarly, timestamp: timestampEarly}
        , {_type: 'TempBasal', rate: 1, date: timestamp, timestamp: timestamp}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
        , profile: { dia: 3, current_basal: 2, bolussnooze_dia_divisor: 2}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    
    hourLater.iob.should.be.lessThan(0);
    hourLater.iob.should.be.greaterThan(-1);
    
  });

  it('should show 0 IOB with Temp Basals if duration is not found', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , timestampEarly = new Date(now - (60 * 60 * 1000)).toISOString()
      , inputs = {
        clock: timestamp
        , history: [{_type: 'TempBasal', rate: 2, date: timestamp, timestamp: timestamp}]
        , profile: {dia: 3, current_basal: 1, bolussnooze_dia_divisor: 2}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    
    hourLater.iob.should.equal(0);
  });

  it('should show 0 IOB with Temp Basals if basal is percentage based', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , timestampEarly = new Date(now - (60 * 60 * 1000)).toISOString()
      , inputs = {
        clock: timestamp
        , history: [{_type: 'TempBasal', temp: 'percent', rate: 2, date: timestamp, timestamp: timestamp},
            {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
        , profile: {dia: 3,current_basal: 1, bolussnooze_dia_divisor: 2}
      };


    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    
    hourLater.iob.should.equal(0);
  });


  it('should calculate IOB using a 4 hour duration', function() {

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , inputs = {
        clock: timestamp
        , history: [{
          _type: 'Bolus'
          , amount: 1
          , timestamp: timestamp
        }]
        , profile: {
          dia: 4
          , bolussnooze_dia_divisor: 2
        }
      };

    var rightAfterBolus = require('../lib/iob')(inputs)[0];
    //console.log(rightAfterBolus);
    rightAfterBolus.iob.should.equal(1);
    rightAfterBolus.bolussnooze.should.equal(1);

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    hourLater.iob.should.be.lessThan(1);
    hourLater.bolussnooze.should.be.lessThan(.5);
    hourLater.iob.should.be.greaterThan(0);

    var after3hInputs = inputs;
    after3hInputs.clock = new Date(now + (3 * 60 * 60 * 1000)).toISOString();
    var after3h = require('../lib/iob')(after3hInputs)[0];
    after3h.iob.should.be.greaterThan(0);

    var after4hInputs = inputs;
    after4hInputs.clock = new Date(now + (4 * 60 * 60 * 1000)).toISOString();
    var after4h = require('../lib/iob')(after4hInputs)[0];
    after4h.iob.should.equal(0);

  });


});
