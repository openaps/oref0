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
        }
      };

    var rightAfterBolus = require('../lib/iob')(inputs);
    rightAfterBolus.iob.should.equal(1);
    rightAfterBolus.bolusiob.should.equal(1);

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs);
    hourLater.iob.should.be.lessThan(1);
    hourLater.bolusiob.should.be.lessThan(.5);
    hourLater.iob.should.be.greaterThan(0);

    var afterDIAInputs = inputs;
    afterDIAInputs.clock = new Date(now + (3 * 60 * 60 * 1000)).toISOString();
    var afterDIA = require('../lib/iob')(afterDIAInputs);

    afterDIA.iob.should.equal(0);
    afterDIA.bolusiob.should.equal(0);

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
        }
      };

    var rightAfterBolus = require('../lib/iob')(inputs);
    rightAfterBolus.iob.should.equal(1);
    rightAfterBolus.bolusiob.should.equal(1);

    var hourLaterInputs = inputs;
    hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
    var hourLater = require('../lib/iob')(hourLaterInputs);
    hourLater.iob.should.be.lessThan(1);
    hourLater.bolusiob.should.be.lessThan(.5);
    hourLater.iob.should.be.greaterThan(0);

    var after3hDIAInputs = inputs;
    after3hDIAInputs.clock = new Date(now + (3 * 60 * 60 * 1000)).toISOString();
    var after3hDIA = require('../lib/iob')(after3hDIAInputs);
    after3hDIA.iob.should.greaterThan(0);

    var after4hDIAInputs = inputs;
    after4hDIAInputs.clock = new Date(now + (4 * 60 * 60 * 1000)).toISOString();
    var after4hDIA = require('../lib/iob')(after4hDIAInputs);
    after4hDIA.iob.should.equal(0);

  });


});