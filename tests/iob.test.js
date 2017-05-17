'use strict';

require('should');

var moment = require('moment');

describe('IOB', function ( ) {

  it('should calculate IOB', function() {

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 1, 'minutes': 0}];

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
          dia: 3, bolussnooze_dia_divisor: 2, basalprofile: basalprofile, current_basal: 1 }

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

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 1, 'minutes': 0}];
    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString()
      , timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString()
      , inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestamp60mAgo}
        , {_type: 'TempBasal', rate: 2, date: timestamp60mAgo, timestamp: timestamp60mAgo}
        , {_type: 'TempBasal', rate: 2, date: timestamp30mAgo, timestamp: timestamp30mAgo}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
        , profile: { dia: 3, current_basal: 1, bolussnooze_dia_divisor: 2, 'basalprofile': basalprofile}
      };

    var iobInputs = inputs;
    iobInputs.clock = timestamp
    var iobNow = require('../lib/iob')(iobInputs)[0];

    //console.log(iobNow);
    iobNow.iob.should.be.lessThan(1);
    iobNow.iob.should.be.greaterThan(0.5);
  });

  it('should calculate IOB with Temp Basals and a basal profile', function() {

    var startingPoint = moment('2016-06-13 01:00:00.000');
    var timestamp = startingPoint.format();
    var timestampEarly = startingPoint.subtract(30,'minutes').format();

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 2, 'minutes': 0},
        {'i': 1, 'start': '01:00:00', 'rate': 1, 'minutes': 60 }];

    var inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly}
        , {_type: 'TempBasal', rate: 2, date: timestampEarly, timestamp: timestampEarly}
        , {_type: 'TempBasal', rate: 2, date: timestamp, timestamp: timestamp}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
        , profile: { dia: 3, bolussnooze_dia_divisor: 2, basalprofile: basalprofile}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = moment('2016-06-13 01:30:00.000');
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    hourLater.iob.should.be.lessThan(0.5);
    hourLater.iob.should.be.greaterThan(0.4);
  });

  it('should calculate IOB with Temp Basals that overlap midnight and a basal profile', function() {

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 2, 'minutes': 0},
        {'i': 1, 'start': '00:15:00', 'rate': 1, 'minutes': 15 },
        {'i': 2, 'start': '00:45:00', 'rate': 0.5, 'minutes': 45 }];

    var startingPoint = moment('2016-06-13 00:15:00.000');
    var timestamp = startingPoint.format();
    var timestampEarly = startingPoint.subtract(30,'minutes').format()
      , inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly}
        , {_type: 'TempBasal', rate: 2, date: timestampEarly, timestamp: timestampEarly}
        , {_type: 'TempBasal', rate: 2, date: timestamp, timestamp: timestamp}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
        , profile: { dia: 3, current_basal: 0.1, bolussnooze_dia_divisor: 2, basalprofile: basalprofile}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = moment('2016-06-13 00:45:00.000'); //new Date(now + (30 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];

    hourLater.iob.should.be.lessThan(0.8);
    hourLater.iob.should.be.greaterThan(0.7);
  });

  it('should calculate IOB with Temp Basals that overlap each other', function() {

    var nowDate = new Date();
    var now = Date.now();

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 1, 'minutes': 0}];

    var startingPoint = moment('2016-06-13 00:30:00.000');
    var timestampEarly = moment('2016-06-13 00:30:00.000').subtract(30,'minutes');
    var timestampEarly2 = moment('2016-06-13 00:30:00.000').subtract(29,'minutes');
    var timestampEarly3 = moment('2016-06-13 00:30:00.000').subtract(28,'minutes');

    var timestamp = startingPoint;
    var inputs = {clock: timestamp,
        history: [
        {_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly.unix()}
        , {_type: 'TempBasal', rate: 2, date: timestampEarly.unix(), timestamp: timestampEarly.format()}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly2.unix()}
        , {_type: 'TempBasal', rate: 2, date: timestampEarly2.unix(), timestamp: timestampEarly2.format()}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly3.unix()}
        , {_type: 'TempBasal', rate: 2, date: timestampEarly3.unix(), timestamp: timestampEarly3.format()}
        , {_type: 'TempBasal', rate: 2, date: timestamp.unix(), timestamp: timestamp.format()}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp.unix()}]
        , profile: { dia: 3, current_basal: 0.1, bolussnooze_dia_divisor: 2, basalprofile: basalprofile}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = moment('2016-06-13 00:30:00.000'); //new Date(now + (30 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];

    hourLater.iob.should.be.lessThan(0.5);
    hourLater.iob.should.be.greaterThan(0.45);
  });
  it('should calculate IOB with Temp Basals that overlap midnight and a basal profile, part deux', function() {

    var nowDate = new Date();
    var now = Date.now();

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 2, 'minutes': 0},
        {'i': 1, 'start': '00:15:00', 'rate': 0.1, 'minutes': 15 },
        {'i': 1, 'start': '00:30:00', 'rate': 2, 'minutes': 30 },
        {'i': 1, 'start': '00:45:00', 'rate': 0.1, 'minutes': 45 }];

    var startingPoint = moment('2016-06-13 23:45:00.000');
    var timestamp = startingPoint.format();
    var timestampEarly = startingPoint.subtract(30,'minutes').format()
      , inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 60, date: timestamp}
        , {_type: 'TempBasal', rate: 2, date: timestamp, timestamp: timestamp} ]
        , profile: { dia: 3, current_basal: 0.1, bolussnooze_dia_divisor: 2, basalprofile: basalprofile}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = moment('2016-06-14 00:45:00.000'); //new Date(now + (30 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];

    hourLater.iob.should.be.lessThan(1);
    hourLater.iob.should.be.greaterThan(0.8);
  });


  it('should not report negative IOB with Temp Basals and a basal profile with drastic changes', function() {

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 0.1, 'minutes': 0},
        {'i': 1, 'start': '00:30:00', 'rate': 2, 'minutes': 30 }];

	var startingPoint = new Date('2016-06-13 00:00:00.000');
	var startingPoint2 = new Date('2016-06-13 00:30:00.000');
	var endPoint = new Date('2016-06-13 01:00:00.000');

    var inputs = {clock: endPoint,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: startingPoint}
        , {_type: 'TempBasal', rate: 0.1, date: startingPoint, timestamp: startingPoint}
        , {_type: 'TempBasal', rate: 2, date: startingPoint2, timestamp: startingPoint2}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: startingPoint2}]
        , profile: { dia: 3, current_basal: 2, bolussnooze_dia_divisor: 2, 'basalprofile': basalprofile}
      };

    var hourLaterInputs = inputs;
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];
    hourLater.iob.should.equal(0);
  });

  it('should calculate IOB with Temp Basal events that overlap', function() {

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 1, 'minutes': 0}];

    var now = Date.now()
      , timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString()
      , timestamp31mAgo = new Date(now - (31 * 60 * 1000)).toISOString()
      , inputs = {clock: timestamp30mAgo,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestamp31mAgo}
        ,{_type: 'TempBasal', rate: 2, date: timestamp31mAgo, timestamp: timestamp31mAgo}
        ,{_type: 'TempBasal', rate: 2, date: timestamp30mAgo, timestamp: timestamp30mAgo}
        ,{_type: 'TempBasalDuration','duration (min)': 30, date: timestamp30mAgo}]
        , profile: { dia: 3, current_basal: 1, 'basalprofile': basalprofile}
      };

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs)[0];

    hourLater.iob.should.be.lessThan(1);
    hourLater.iob.should.be.greaterThan(0);

  });

  it('should calculate IOB with Temp Basals that are lower than base rate', function() {

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 2, 'minutes': 0}];

    var now = Date.now()
      , timestamp = new Date(now).toISOString()
      , timestampEarly = new Date(now - (30 * 60 * 1000)).toISOString()
      , inputs = {clock: timestamp,
        history: [{_type: 'TempBasalDuration','duration (min)': 30, date: timestampEarly}
        , {_type: 'TempBasal', rate: 1, date: timestampEarly, timestamp: timestampEarly}
        , {_type: 'TempBasal', rate: 1, date: timestamp, timestamp: timestamp}
        , {_type: 'TempBasalDuration','duration (min)': 30, date: timestamp}]
        , profile: { dia: 3, current_basal: 2, bolussnooze_dia_divisor: 2, 'basalprofile': basalprofile}
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

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 1, 'minutes': 0}];

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
		  , basalprofile: basalprofile
		  , current_basal: 1
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
