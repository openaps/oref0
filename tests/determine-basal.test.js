'use strict';

require('should');

describe('setTempBasal', function ( ) {
    var determinebasal = require('../bin/oref0-determine-basal')();

   //function setTempBasal(rate, duration, profile, requestedTemp)

    var profile = { "current_basal":0.8,"max_daily_basal":1.3,"max_basal":3.0 };
    var rt = {};
    it('should cancel temp', function () {
        var requestedTemp = determinebasal.setTempBasal(0, 0, profile, rt);
        requestedTemp.rate.should.equal(0);
        requestedTemp.duration.should.equal(0);
    });

    it('should set zero temp', function () {
        var requestedTemp = determinebasal.setTempBasal(0, 30, profile, rt);
        requestedTemp.rate.should.equal(0);
        requestedTemp.duration.should.equal(30);
    });

    it('should set high temp', function () {
        var requestedTemp = determinebasal.setTempBasal(2, 30, profile, rt);
        requestedTemp.rate.should.equal(2);
        requestedTemp.duration.should.equal(30);
    });

    it('should limit high temp to max_basal', function () {
        var requestedTemp = determinebasal.setTempBasal(4, 30, profile, rt);
        requestedTemp.rate.should.equal(3);
        requestedTemp.duration.should.equal(30);
    });

    it('should set current_basal as temp on requestedTemp if offline', function () {
        var requestedTemp = determinebasal.setTempBasal(0, 0, profile, rt, "Offline");
        requestedTemp.rate.should.equal(0.8);
        requestedTemp.duration.should.equal(30);
    });

    it('should limit high temp to 3 * max_daily_basal', function () {
        var profile = { "current_basal":1.0,"max_daily_basal":1.3,"max_basal":10.0 };
        var requestedTemp = determinebasal.setTempBasal(6, 30, profile, rt);
        requestedTemp.rate.should.equal(3.9);
        requestedTemp.duration.should.equal(30);
    });

    it('should limit high temp to 4 * current_basal', function () {
        var profile = { "current_basal":0.7,"max_daily_basal":1.3,"max_basal":10.0 };
        var requestedTemp = determinebasal.setTempBasal(6, 30, profile, rt);
        requestedTemp.rate.should.equal(2.8);
        requestedTemp.duration.should.equal(30);
    });

});

describe('determine-basal', function ( ) {
    var determinebasal = require('../bin/oref0-determine-basal')();

   //function determine_basal(glucose_status, currenttemp, iob_data, profile)

    // standard initial conditions for all determine-basal test cases unless overridden
    var glucose_status = {"delta":0,"glucose":115,"avgdelta":0};
    var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
    var iob_data = {"iob":0,"activity":0,"bolusiob":0};
    var profile = {"max_iob":1.5,"dia":3,"type":"current","current_basal":0.9,"max_daily_basal":1.3,"max_basal":3.5,"max_bg":120,"min_bg":110,"sens":40};

    it('should do nothing when in range w/o IOB', function () {
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/in range/);
    });

    it('should set current temp when in range w/o IOB with Offline set', function () {
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile, 'Offline');
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        output.reason.should.match(/in range.*setting current basal/);
    });

    // low glucose suspend test cases
    it('should temp to 0 when low w/o IOB', function () {
        var glucose_status = {"delta":-5,"glucose":75,"avgdelta":-5};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 75<80/);
    });

    it('should do nothing when low and rising w/o IOB', function () {
        var glucose_status = {"delta":5,"glucose":75,"avgdelta":5};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/75<80.*no high-temp/);
    });

    it('should do nothing when low and rising w/ negative IOB', function () {
        var glucose_status = {"delta":5,"glucose":75,"avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/75<80.*no high-temp/);
    });

    it('should do nothing on uptick even if avgdelta is still negative', function () {
        var glucose_status = {"delta":1,"glucose":75,"avgdelta":-2};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/BG 75<80/);
    });

    it('should temp to 0 when rising slower than BGI', function () {
        var glucose_status = {"delta":1,"glucose":75,"avgdelta":1};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 75<80/);
    });

    it('should temp to 0 when low and falling, regardless of BGI', function () {
        var glucose_status = {"delta":-1,"glucose":75,"avgdelta":-1};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0.5};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 75<80/);
    });

    it('should cancel high-temp when low and rising faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var glucose_status = {"delta":5,"glucose":75,"avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/BG 75<80/);
    });

    it('should high-temp when > 80-ish and rising w/ lots of negative IOB', function () {
        var glucose_status = {"delta":5,"glucose":85,"avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });

    // low eventualBG

    it('should low-temp when eventualBG < min_bg', function () {
        var glucose_status = {"delta":-3,"glucose":110,"avgdelta":-1};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.below(0.8);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*<110/);
    });

    it('should cancel low-temp when lowish and rising faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":0.5,"temp":"absolute"};
        var glucose_status = {"delta":3,"glucose":85,"avgdelta":3};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/Eventual BG.*<.*but Delta.*> BGI.*; cancel/);
    });

    it('should low-temp when low and rising slower than BGI', function () {
        var glucose_status = {"delta":1,"glucose":85,"avgdelta":1};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.below(0.8);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });

    // high eventualBG

    it('should high-temp when eventualBG > max_bg', function () {
        var glucose_status = {"delta":+3,"glucose":120,"avgdelta":+1};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*>120/);
    });

    it('should cancel high-temp when high and falling faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":175,"avgdelta":-5};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/Eventual BG.*>.*but Delta.*< BGI.*; cancel/);
    });

    it('should high-temp when high and falling slower than BGI', function () {
        var glucose_status = {"delta":-1,"glucose":175,"avgdelta":-1};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });

    it('should handle NS sgv fields', function () {
      var glucose_status = determinebasal.getLastGlucose([{sgv: 100}, {sgv: 95}, {sgv: 90}, {sgv: 70}]);
      glucose_status.delta.should.equal(5);
      glucose_status.glucose.should.equal(100);
      glucose_status.avgdelta.should.equal(10);
    });


});
