'use strict';

require('should');


describe('tempBasalFunctions.setTempBasal', function ( ) {
    var tempBasalFunctions = require('../lib/basal-set-temp');

   //function tempBasalFunctions.setTempBasal(rate, duration, profile, requestedTemp)

    var profile = { "current_basal":0.8,"max_daily_basal":1.3,"max_basal":3.0 };
    var rt = {};
    it('should cancel temp', function () {
        var requestedTemp = tempBasalFunctions.setTempBasal(0, 0, profile, rt);
        requestedTemp.rate.should.equal(0);
        requestedTemp.duration.should.equal(0);
    });

    it('should set zero temp', function () {
        var requestedTemp = tempBasalFunctions.setTempBasal(0, 30, profile, rt);
        requestedTemp.rate.should.equal(0);
        requestedTemp.duration.should.equal(30);
    });

    it('should set high temp', function () {
        var requestedTemp = tempBasalFunctions.setTempBasal(2, 30, profile, rt);
        requestedTemp.rate.should.equal(2);
        requestedTemp.duration.should.equal(30);
    });

    it('should not set basal on skip neutral mode', function () {
        profile.skip_neutral_temps = true;
        var rt2 = {};
        var current = {duration: 10};
        var requestedTemp = tempBasalFunctions.setTempBasal(0.8, 30, profile, rt2, current);
        requestedTemp.duration.should.equal(0);
        var requestedTemp = tempBasalFunctions.setTempBasal(0.8, 30, profile, {});
        requestedTemp.reason.should.equal('Suggested rate is same as profile rate, no temp basal is active, doing nothing');
    });

    it('should limit high temp to max_basal', function () {
        var requestedTemp = tempBasalFunctions.setTempBasal(4, 30, profile, rt);
        requestedTemp.rate.should.equal(3);
        requestedTemp.duration.should.equal(30);
    });

    it('should limit high temp to 3 * max_daily_basal', function () {
        var profile = { "current_basal":1.0,"max_daily_basal":1.3,"max_basal":10.0 };
        var requestedTemp = tempBasalFunctions.setTempBasal(6, 30, profile, rt);
        requestedTemp.rate.should.equal(3.9);
        requestedTemp.duration.should.equal(30);
    });

    it('should limit high temp to 4 * current_basal', function () {
        var profile = { "current_basal":0.7,"max_daily_basal":1.3,"max_basal":10.0 };
        var requestedTemp = tempBasalFunctions.setTempBasal(6, 30, profile, rt);
        requestedTemp.rate.should.equal(2.8);
        requestedTemp.duration.should.equal(30);
    });
    
    it('should temp to 0 when requested rate is less then 0 * current_basal', function () {
        var profile = { "current_basal":0.7,"max_daily_basal":1.3,"max_basal":10.0 };
        var requestedTemp = tempBasalFunctions.setTempBasal(-1, 30, profile, rt);
        requestedTemp.rate.should.equal(0);
        requestedTemp.duration.should.equal(30);
    });

    it('should limit high temp to 4 * max_daily_basal when overridden', function () {
        var profile = { "current_basal":2.0,"max_daily_basal":1.3,"max_basal":10.0, "max_daily_safety_multiplier": 4};
        var requestedTemp = tempBasalFunctions.setTempBasal(6, 30, profile, rt);
        requestedTemp.rate.should.equal(5.2);
        requestedTemp.duration.should.equal(30);
    });

    it('should limit high temp to 5 * current_basal when overridden', function () {
        var profile = { "current_basal":0.7,"max_daily_basal":1.3,"max_basal":10.0, "current_basal_safety_multiplier": 5};
        var requestedTemp = tempBasalFunctions.setTempBasal(6, 30, profile, rt);
        requestedTemp.rate.should.equal(3.5);
        requestedTemp.duration.should.equal(30);
    });

    it('should allow small basal change when current temp is also small', function () {
        var rt = {}
        var profile = { "current_basal":0.075,"max_daily_basal":1.3,"max_basal":10.0, "current_basal_safety_multiplier": 5, "model": "523"};
        var currentTemp = { "rate": 0.025, "duration": 24};
        var requestedTemp = tempBasalFunctions.setTempBasal(0, 30, profile, rt, currentTemp);
        requestedTemp.rate.should.equal(0);
        requestedTemp.duration.should.equal(30);
    });

    it('should not allow small basal change when current temp is large', function () {
        var rt = {}
        var profile = { "current_basal":10.075,"max_daily_basal":11.3,"max_basal":50.0, "current_basal_safety_multiplier": 5, "model": "523"};
        var currentTemp = { "rate": 10.1, "duration": 24};
        var requestedTemp = tempBasalFunctions.setTempBasal(10.125, 30, profile, rt, currentTemp);
        //requestedTemp.reason.should.equal("undefined, but 24m left and 10.1 ~ req 10.1U/hr: no action required");
    });
});
