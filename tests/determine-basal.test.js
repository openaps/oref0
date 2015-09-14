'use strict';

require('should');

describe('setTempBasal', function ( ) {
  var determinebasal = require('../bin/determine-basal')();

   //function setTempBasal(rate, duration, profile, requestedTemp)

  it('should cancel temp', function () {
    var profile = { "current_basal":1.0,"max_daily_basal":1.3,"max_basal":3.0 };
    var requestedTemp = {};
    //console.error(JSON.stringify(profile));
    var cancel = determinebasal.setTempBasal(0, 0, profile, requestedTemp);
    //console.error(JSON.stringify(cancel));
    cancel.rate.should.equal(0);
    cancel.duration.should.equal(0);
  });

  it('should set zero temp', function () {
    var profile = { "current_basal":1.0,"max_daily_basal":1.3,"max_basal":3.0 };
    var requestedTemp = {};
    //console.error(JSON.stringify(profile));
    var cancel = determinebasal.setTempBasal(0, 30, profile, requestedTemp);
    //console.error(JSON.stringify(cancel));
    cancel.rate.should.equal(0);
    cancel.duration.should.equal(30);
  });

  it('should set high temp', function () {
    var profile = { "current_basal":1.0,"max_daily_basal":1.3,"max_basal":3.0 };
    var requestedTemp = {};
    //console.error(JSON.stringify(profile));
    var cancel = determinebasal.setTempBasal(2, 30, profile, requestedTemp);
    //console.error(JSON.stringify(cancel));
    cancel.rate.should.equal(2);
    cancel.duration.should.equal(30);
  });

  it('should limit high temp to max_basal', function () {
    var profile = { "current_basal":1.0,"max_daily_basal":1.3,"max_basal":3.0 };
    var requestedTemp = {};
    //console.error(JSON.stringify(profile));
    var cancel = determinebasal.setTempBasal(4, 30, profile, requestedTemp);
    //console.error(JSON.stringify(cancel));
    cancel.rate.should.equal(3);
    cancel.duration.should.equal(30);
  });

  it('should limit high temp to 3 * max_daily_basal', function () {
    var profile = { "current_basal":1.0,"max_daily_basal":1.3,"max_basal":10.0 };
    var requestedTemp = {};
    //console.error(JSON.stringify(profile));
    var cancel = determinebasal.setTempBasal(6, 30, profile, requestedTemp);
    //console.error(JSON.stringify(cancel));
    cancel.rate.should.equal(3.9);
    cancel.duration.should.equal(30);
  });

  it('should limit high temp to 4 * current_basal', function () {
    var profile = { "current_basal":0.7,"max_daily_basal":1.3,"max_basal":10.0 };
    var requestedTemp = {};
    //console.error(JSON.stringify(profile));
    var cancel = determinebasal.setTempBasal(6, 30, profile, requestedTemp);
    //console.error(JSON.stringify(cancel));
    cancel.rate.should.equal(2.8);
    cancel.duration.should.equal(30);
  });

  it('should set current_basal as temp on cancel if offline', function () {
    var profile = { "current_basal":0.7,"max_daily_basal":1.3,"max_basal":10.0 };
    var requestedTemp = {};
    //console.error(JSON.stringify(profile));
    var cancel = determinebasal.setTempBasal(0, 0, profile, requestedTemp, "Offline");
    //console.error(JSON.stringify(cancel));
    cancel.rate.should.equal(0.7);
    cancel.duration.should.equal(30);
  });

});
