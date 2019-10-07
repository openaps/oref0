'use strict';

var should = require('should');

describe('round_basal', function ( ) {
    var round_basal = require('../lib/round-basal');

    it('should round correctly without profile being passed in', function() {
        var basal = 0.025;
        var output = round_basal(basal);
        output.should.equal(0.05);
    });

    var profile = {model: "522"};
    it('should round correctly with an old pump model', function() {
        var basal = 0.025;
        var output = round_basal(basal, profile);
        output.should.equal(0.05);
    });


    it('should round correctly with a new pump model', function() {
        var basal = 0.025;
        profile.model = "554";
        var output = round_basal(basal, profile);
        output.should.equal(0.025);
        //console.error(output);
    });

    it('should round correctly with an invalid pump model', function() {
        var basal = 0.025;
        profile.model = "HelloThisIsntAPumpModel";
        var output = round_basal(basal, profile);
        output.should.equal(0.05);
    });

    var data = [
        { basal: 0.83, rounded: 0.85},
        { basal: 0.86, rounded: 0.85},
        { basal: 1.83, rounded: 1.85},
        { basal: 1.86, rounded: 1.85},
        { basal: 10.83, rounded: 10.8},
        { basal: 10.86, rounded: 10.9}
    ];

    data.forEach(function (rate) {
        it('should round basal rates properly (' + rate.basal + ' -> ' + rate.rounded + ')', function () {
            var output = round_basal(rate.basal);
            output.should.equal(rate.rounded);
        });
    });
});

describe('determine-basal', function ( ) {
    var determine_basal = require('../lib/determine-basal/determine-basal');
    var tempBasalFunctions = require('../lib/basal-set-temp');

   //function determine_basal(glucose_status, currenttemp, iob_data, profile)

    // standard initial conditions for all determine-basal test cases unless overridden
    var glucose_status = {"delta":0,"glucose":115,"long_avgdelta":1.1,"short_avgdelta":0};
    var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
    var iob_data = {"iob":0,"activity":0,"bolussnooze":0};
    var autosens = {"ratio":1.0};
    var profile = {"max_iob":2.5,"dia":3,"type":"current","current_basal":0.9,"max_daily_basal":1.3,"max_basal":3.5,"max_bg":120,"min_bg":110,"sens":40,"carb_ratio":10};
    var meal_data = {"carbs":50,"nsCarbs":50,"bwCarbs":0,"journalCarbs":0,"mealCOB":0,"currentDeviation":0,"maxDeviation":0,"minDeviation":0,"slopeFromMaxDeviation":0,"slopeFromMinDeviation":0,"allDeviations":[0,0,0,0,0],"bwFound":false}

    it('should cancel high temp when in range w/o IOB', function () {
        var currenttemp = {"duration":30,"rate":1.5,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //output.rate.should.equal(0);
        //output.duration.should.equal(0);
        //console.error(output);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        //output.reason.should.match(/in range.*/);
    });

    //it('should let low temp run in range w/o IOB', function () {
        //var currenttemp = {"duration":30,"rate":0,"temp":"absolute"};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.error(output);
        //(typeof output.rate).should.equal('undefined');
        //(typeof output.duration).should.equal('undefined');
        //output.reason.should.match(/.*letting low.*/);
    //});

    // low glucose suspend test cases
    it('should temp to 0 when low w/o IOB', function () {
        var glucose_status = {"delta":-5,"glucose":75,"long_avgdelta":-5,"short_avgdelta":-5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(0);
        output.duration.should.be.above(29);
        //output.reason.should.match(/BG 75<80/);
    });

    it('should not extend temp to 0 when <10m elapsed', function () {
        var currenttemp = {"duration":57,"rate":0,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":75,"long_avgdelta":-5,"short_avgdelta":-5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
    });

    it('should do nothing when low and rising w/o IOB', function () {
        var glucose_status = {"delta":6,"glucose":75,"long_avgdelta":6,"short_avgdelta":6};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        //output.reason.should.match(/75<80.*setting current basal/);
    });

    //it('should do nothing when low and rising w/ negative IOB', function () {
        //var glucose_status = {"delta":5,"glucose":75,"long_avgdelta":5,"short_avgdelta":5};
        //var iob_data = {"iob":-1,"activity":-0.01,"bolussnooze":0};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0.9);
        //output.duration.should.equal(30);
        //output.reason.should.match(/75<80.*setting current basal/);
    //});

    //it('should do nothing on large uptick even if avgdelta is still negative', function () {
        //var glucose_status = {"delta":4,"glucose":75,"long_avgdelta":-2,"short_avgdelta":-2};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0.9);
        //output.duration.should.equal(30);
        //output.reason.should.match(/BG 75<80/);
    //});

    it('should temp to zero when rising slower than BGI', function () {
        var glucose_status = {"delta":1,"glucose":75,"long_avgdelta":1,"short_avgdelta":1};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        //output.reason.should.match(/BG 75<80/);
    });

    it('should temp to 0 when low and falling, regardless of BGI', function () {
        var glucose_status = {"delta":-1,"glucose":75,"long_avgdelta":-1,"short_avgdelta":-1};
        var iob_data = {"iob":1,"activity":0.01,"bolussnooze":0.5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.equal(0);
        output.duration.should.be.above(29);
        //output.reason.should.match(/BG 75<80/);
    });

    //it('should cancel high-temp when low and rising faster than BGI', function () {
        //var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        //var glucose_status = {"delta":5,"glucose":75,"long_avgdelta":5,"short_avgdelta":5};
        //var iob_data = {"iob":-1,"activity":-0.01,"bolussnooze":0};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0.9);
        //output.duration.should.equal(30);
        //output.reason.should.match(/BG 75<80, min delta .*/);
    //});

    //it('should cancel low-temp when eventualBG is higher then max_bg', function () {
        //var currenttemp = {"duration":20,"rate":0,"temp":"absolute"};
        //var glucose_status = {"delta":5,"glucose":75,"long_avgdelta":5,"short_avgdelta":5};
        //var iob_data = {"iob":-1,"activity":-0.01,"bolussnooze":0};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0.9);
        //output.duration.should.equal(30);
        //output.reason.should.match(/BG 75<80, min delta .*/);
    //});

    it('should high-temp when > 80-ish and rising w/ lots of negative IOB', function () {
        var glucose_status = {"delta":5,"glucose":85,"long_avgdelta":5,"short_avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });

    it('should high-temp when > 180-ish and rising but not more then maxSafeBasal', function () {
        var glucose_status = {"delta":5,"glucose":185,"long_avgdelta":5,"short_avgdelta":5};
        var iob_data = {"iob":0,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.reason.should.match(/.*, adj. req. rate:.* to maxSafeBasal:.*, no temp, setting/);
    });

    it('should reduce high-temp when schedule would be above max', function () {
        var glucose_status = {"delta":5,"glucose":145,"long_avgdelta":5,"short_avgdelta":5};
        var currenttemp = {"duration":160,"rate":1.9,"temp":"absolute"};
        var iob_data = {"iob":0,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.duration.should.equal(30);
        output.reason.should.match(/.* > 2.*insulinReq. Setting temp.*/);
    });

    it('should continue high-temp when required ~= temp running', function () {
        var glucose_status = {"delta":5,"glucose":145,"long_avgdelta":5,"short_avgdelta":5};
        var currenttemp = {"duration":30,"rate":3.5,"temp":"absolute"};
        var iob_data = {"iob":0,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/Eventual BG .*>.*, temp .* >~ req /);
    });

    it('should set high-temp when required running temp is low', function () {
        var glucose_status = {"delta":5,"glucose":145,"long_avgdelta":5,"short_avgdelta":5};
        var currenttemp = {"duration":30,"rate":1.1,"temp":"absolute"};
        var iob_data = {"iob":0,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*>.*, temp/);
    });

    it('should stop high-temp when iob is near max_iob.', function () {
        var glucose_status = {"delta":5,"glucose":485,"long_avgdelta":5,"short_avgdelta":5};
        var iob_data = {"iob":3.5,"activity":0.05,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        output.reason.should.match(/IOB .* > max_iob .*/);
    });

    it('should temp to 0 when LOW w/ positive IOB', function () {
        var glucose_status = {"delta":0,"glucose":39,"long_avgdelta":-1.1,"short_avgdelta":0};
        var iob_data = {"iob":1,"activity":0.01,"bolussnooze":0.5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.equal(0);
        output.duration.should.be.above(29);
        //output.reason.should.match(/BG 39<80/);
    });

    it('should low temp when LOW w/ negative IOB', function () {
        var glucose_status = {"delta":0,"glucose":39,"long_avgdelta":-1.1,"short_avgdelta":0};
        var iob_data = {"iob":-2.5,"activity":-0.03,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.be.below(0.8);
        output.duration.should.be.above(29);
        //output.reason.should.match(/BG 39<80/);
    });

    it('should temp to 0 when LOW w/ no IOB', function () {
        var glucose_status = {"delta":0,"glucose":39,"long_avgdelta":-1.1,"short_avgdelta":0};
        var iob_data = {"iob":0,"activity":0,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.equal(0);
        output.duration.should.be.above(29);
        //output.reason.should.match(/BG 39<80/);
    });



    // low eventualBG

    it('should low-temp when eventualBG < min_bg', function () {
        var glucose_status = {"delta":-3,"glucose":110,"long_avgdelta":-1,"short_avgdelta":-1};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.be.below(0.8);
        output.duration.should.be.above(29);
        output.reason.should.match(/Eventual BG .*< 110.*/);
    });

    it('should low-temp when eventualBG < min_bg with delta > exp. delta', function () {
        var glucose_status = {"delta":-5,"glucose":115,"long_avgdelta":-6,"short_avgdelta":-6};
        var iob_data = {"iob":2,"activity":0.05,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.be.below(0.2);
        output.duration.should.be.above(29);
        //output.reason.should.match(/Eventual BG .*< 110.*setting .*/);
    });

    it('should low-temp when eventualBG < min_bg with delta > exp. delta', function () {
        var glucose_status = {"delta":-2,"glucose":156,"long_avgdelta":-1.33,"short_avgdelta":-1.33};
        var iob_data = {"iob":3.51,"activity":0.06,"bolussnooze":0.08};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.be.below(0.8);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*< 110.*setting .*/);
    });

    it('should low-temp much less when eventualBG < min_bg with delta barely negative', function () {
        var glucose_status = {"delta":-1,"glucose":115,"long_avgdelta":-1,"short_avgdelta":-1};
        var iob_data = {"iob":2,"activity":0.05,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.above(0.3);
        output.rate.should.be.below(0.8);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*< 110.*setting .*/);
    });

    //it('should do nothing when eventualBG < min_bg but appropriate low temp in progress', function () {
        //var glucose_status = {"delta":-1,"glucose":110,"long_avgdelta":-1,"short_avgdelta":-1};
        //var currenttemp = {"duration":20,"rate":0.25,"temp":"absolute"};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        ////console.log(output);
        //(typeof output.rate).should.equal('undefined');
        //(typeof output.duration).should.equal('undefined');
        //output.reason.should.match(/Eventual BG .*< 110, temp .*/);
    //});

    it('should cancel low-temp when lowish and avg.delta rising faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":0.5,"temp":"absolute"};
        var glucose_status = {"delta":3,"glucose":85,"long_avgdelta":3,"short_avgdelta":3};
        var iob_data = {"iob":-0.7,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.above(0.8);
        output.duration.should.equal(30);
        //output.rate.should.equal(0);
        //output.duration.should.equal(0);
        //output.reason.should.match(/.*; cancel/);
    });

    it('should cancel low-temp when lowish and delta rising faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":0.5,"temp":"absolute"};
        var glucose_status = {"delta":3,"glucose":85,"long_avgdelta":3,"short_avgdelta":3};
        var iob_data = {"iob":-0.7,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.be.above(0.8);
        output.duration.should.equal(30);
    });

    it('should set current basal as temp when lowish and delta rising faster than BGI', function () {
        var currenttemp = {"duration":0,"rate":0.5,"temp":"absolute"};
        var glucose_status = {"delta":3,"glucose":85,"long_avgdelta":3,"short_avgdelta":3};
        var iob_data = {"iob":-0.7,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //(typeof output.rate).should.equal('undefined');
        //(typeof output.duration).should.equal('undefined');
        //console.log(profile, output);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        output.reason.should.match(/in range.*setting current basal/);
    });


    it('should low-temp when low and rising slower than BGI', function () {
        var glucose_status = {"delta":1,"glucose":85,"long_avgdelta":1,"short_avgdelta":1};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.below(0.8);
        output.duration.should.equal(30);
        //output.reason.should.match(/setting/);
    });

    // high eventualBG

    it('should high-temp when eventualBG > max_bg', function () {
        var glucose_status = {"delta":+3,"glucose":120,"long_avgdelta":0,"short_avgdelta":+1};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*>= 120/);
    });

    it('should cancel high-temp when high and avg. delta falling faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":175,"long_avgdelta":-5,"short_avgdelta":-5};
        var iob_data = {"iob":1,"activity":0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        //output.reason.should.match(/.*; cancel/);
        //output.rate.should.equal(0);
        //output.duration.should.equal(0);
        output.reason.should.match(/Eventual BG.*>.*but Min. Delta.*< Exp.*/);
    });

    it('should cancel high-temp when high and delta falling faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":175,"long_avgdelta":-4,"short_avgdelta":-4};
        var iob_data = {"iob":1,"activity":0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG.*>.*but.*Delta.*< Exp.*/);
    });

    it('should do nothing when no temp and high and delta falling faster than BGI', function () {
        var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":175,"long_avgdelta":-4,"short_avgdelta":-4};
        var iob_data = {"iob":1,"activity":0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //(typeof output.rate).should.equal('undefined');
        //(typeof output.duration).should.equal('undefined');
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG.*>.*but.*Delta.*< Exp.*/);
    });

    it('should high-temp when high and falling slower than BGI', function () {
        var glucose_status = {"delta":-1,"glucose":175,"long_avgdelta":-1,"short_avgdelta":-1};
        var iob_data = {"iob":1,"activity":0.01,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });

    it('should high-temp when high and falling slowly with low insulin activity', function () {
        var glucose_status = {"delta":-1,"glucose":300,"long_avgdelta":-1,"short_avgdelta":-1};
        var iob_data = {"iob":0.5,"activity":0.005,"bolussnooze":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.above(2.5);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });

    //it('should set lower high-temp when high and falling almost fast enough with low insulin activity', function () {
        //var glucose_status = {"delta":-6,"glucose":300,"long_avgdelta":-5,"short_avgdelta":-5};
        //var iob_data = {"iob":0.5,"activity":0.005,"bolussnooze":0};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.error(output);
        //output.rate.should.be.above(1);
        //output.rate.should.be.below(2);
        //output.duration.should.equal(30);
        //output.reason.should.match(/no temp, setting/);
    //});

    //it('should reduce high-temp when high and falling almost fast enough with low insulin activity', function () {
        //var glucose_status = {"delta":-6,"glucose":300,"long_avgdelta":-5,"short_avgdelta":-5};
        //var iob_data = {"iob":0.5,"activity":0.005,"bolussnooze":0};
        //var currenttemp = {"duration":30,"rate":3.5,"temp":"absolute"};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.error(output);
        //output.rate.should.be.above(1);
        //output.rate.should.be.below(2);
        //output.duration.should.equal(30);
        //output.reason.should.match(/.* > 2.*insulinReq. Setting temp.*/);
    //});

    it('should profile.current_basal be undefined return error', function () {
      var result = determine_basal(undefined,undefined,undefined,undefined);
      result.error.should.equal('Error: could not get current basal rate');
    });

    it('should let low-temp run when bg < 30 (Dexcom is in ???)', function () {
        var currenttemp = {"duration":30,"rate":0,"temp":"absolute"};
        var output = determine_basal({glucose:10},currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        (typeof output.rate).should.equal('undefined');
        output.reason.should.match(/CGM is calibrating/);
    });

    it('should cancel high-temp when bg < 30 (Dexcom is in ???)', function () {
        var currenttemp = {"duration":30,"rate":2,"temp":"absolute"};
        var output = determine_basal({glucose:10},currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.be.below(1);
        output.reason.should.match(/Replacing high temp/);
    });

    it('profile should contain min_bg,max_bg', function () {
      var result = determine_basal({glucose:100},undefined, undefined, {"current_basal":0.0}, autosens, meal_data, tempBasalFunctions);
      result.error.should.equal('Error: could not determine target_bg. ');
    });

    it('iob_data should not be undefined', function () {
      var result = determine_basal({glucose:100},undefined, undefined, {"current_basal":0.0, "max_bg":100,"min_bg":1100}, autosens, meal_data, tempBasalFunctions);
      result.error.should.equal('Error: iob_data undefined. ');
    });

    //it('iob_data should contain activity, iob, bolussnooze', function () {
      //var result = determine_basal({glucose:100}, undefined,{"activity":0}, {"current_basal":0.0, "max_bg":100,"min_bg":110}, autosens, meal_data, tempBasalFunctions);
      //result.error.should.equal('Error: iob_data missing some property. ');
    //});

/*
    it('should return error eventualBG if something went wrong', function () {
      var result = determine_basal({glucose:100}, undefined,{"activity":0, "iob":0,"bolussnooze":0}, {"current_basal":0.0, "sens":NaN}, autosens, meal_data, tempBasalFunctions);
      result.error.should.equal('Error: could not calculate eventualBG');
    });
*/

    // meal assist / bolus snooze
    // right after 20g 1U meal bolus
    //it('should set current basal as temp when low and rising after meal bolus', function () {
        //var glucose_status = {"delta":1,"glucose":80,"long_avgdelta":1,"short_avgdelta":1};
        //var iob_data = {"iob":0.5,"activity":-0.01,"bolussnooze":1,"basaliob":-0.5};
        //var meal_data = {"carbs":20,"boluses":1, "mealCOB":20};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0.9);
        //output.duration.should.equal(30);
    //});

    it('should do nothing when requested temp already running with >15m left', function () {
        var glucose_status = {"delta":-2,"glucose":121,"long_avgdelta":-1.333,"short_avgdelta":-1.333};
        var iob_data = {"iob":3.983,"activity":0.0255,"bolussnooze":2.58,"basaliob":0.384,"netbasalinsulin":0.3,"hightempinsulin":0.7};
        var meal_data = {"carbs":65,"boluses":4, "mealCOB":65};
        var currenttemp = {"duration":29,"rate":1.3,"temp":"absolute"};
        var profile = {"max_iob":3,"type":"current","dia":3,"current_basal":1.3,"max_daily_basal":1.3,"max_basal":3.5,"min_bg":105,"max_bg ":105,"sens":40,"carb_ratio":10}
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
    });

    //it('should cancel high temp when low and dropping after meal bolus', function () {
        //var glucose_status = {"delta":-1,"glucose":80,"long_avgdelta":1,"short_avgdelta":1};
        //var iob_data = {"iob":0.5,"activity":-0.01,"bolussnooze":1,"basaliob":-0.5};
        //var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        ////console.log(output);
        ////output.rate.should.equal(0);
        ////output.duration.should.equal(0);
        //output.rate.should.be.below(1.0);
        //output.duration.should.equal(30);
    //});

    //it('should cancel low temp when low and rising after meal bolus', function () {
        //var glucose_status = {"delta":1,"glucose":80,"long_avgdelta":1,"short_avgdelta":1};
        //var iob_data = {"iob":0.5,"activity":-0.01,"bolussnooze":1,"basaliob":-0.5};
        //var currenttemp = {"duration":20,"rate":0,"temp":"absolute"};
        //var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        ////console.log(output);
        //output.rate.should.equal(0.9);
        //output.duration.should.equal(30);
        ////output.rate.should.equal(0);
        ////output.duration.should.equal(0);
    //});

    /* TODO: figure out how to do tests for advanced-meal-assist
    // 40m after 20g 1U meal bolus
    it('should high-temp aggressively when 120 and rising after meal bolus', function () {
        var glucose_status = {"delta":10,"glucose":120,"avgdelta":10};
        var iob_data = {"iob":0.4,"activity":0,"bolussnooze":0.7,"basaliob":-0.3};
        var meal_data = {"carbs":20,"boluses":1, "mealCOB":20};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        console.log(output);
        output.rate.should.be.above(1.8);
        output.duration.should.equal(30);
    });

    // 60m after 20g 1U meal bolus
    it('should high-temp aggressively when 150 and rising after meal bolus', function () {
        var glucose_status = {"delta":3,"glucose":150,"avgdelta":5};
        var iob_data = {"iob":0.5,"activity":0.01,"bolussnooze":0.6,"basaliob":-0.1};
        var meal_data = {"carbs":20,"boluses":1, "mealCOB":20};
        var currenttemp = {"duration":10,"rate":2,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        console.log(output);
        output.rate.should.be.above(2.2);
        output.duration.should.equal(30);
    });

    // 75m after 20g 1U meal bolus
    it('should reduce high-temp when 160 and dropping slowly after meal bolus', function () {
        var glucose_status = {"delta":-3,"glucose":160,"avgdelta":0};
        var iob_data = {"iob":0.9,"activity":0.02,"bolussnooze":0.5,"basaliob":0.4};
        var meal_data = {"carbs":20,"boluses":1, "mealCOB":20};
        var currenttemp = {"duration":30,"rate":2.5,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.be.below(1.5);
    });

    // right after 120g 6U meal bolus
    it('should high-temp when 120 and rising after meal bolus', function () {
        var glucose_status = {"delta":4,"glucose":120,"avgdelta":4};
        var iob_data = {"iob":6,"activity":0,"bolussnooze":6,"basaliob":0,"hightempinsulin":0};
        var meal_data = {"carbs":120,"boluses":6, "mealCOB":120};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        console.log(output);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
    });

    // after 120g 6U meal bolus
    it('should high-temp when 140 and rising after meal bolus', function () {
        var glucose_status = {"delta":4,"glucose":140,"avgdelta":4};
        var iob_data = {"iob":6.5,"activity":0.01,"bolussnooze":5.5,"basaliob":1,"hightempinsulin":1};
        var meal_data = {"carbs":120,"boluses":6, "mealCOB":100};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        console.log(output);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
    });

    // after 120g 6U meal bolus
    it('should high-temp when 160 and rising after meal bolus', function () {
        var glucose_status = {"delta":4,"glucose":160,"avgdelta":4};
        var iob_data = {"iob":7.0,"activity":0.02,"bolussnooze":5.0,"basaliob":2,"hightempinsulin":2};
        var meal_data = {"carbs":120,"boluses":6, "mealCOB":80};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        console.log(output);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
    });

    // after 120g 6U meal bolus
    it('should not high-temp when 160 and rising slowly after meal bolus', function () {
        var glucose_status = {"delta":1,"glucose":160,"avgdelta":1};
        var iob_data = {"iob":7.0,"activity":0.02,"bolussnooze":5.0,"basaliob":2};
        var meal_data = {"carbs":120,"boluses":6, "mealCOB":80};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        console.log(output);
        //should.not.exist(output.rate);
        //should.not.exist(output.duration);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
    });

    // after 120g 6U meal bolus
    it('should cancel temp when 160 and falling after meal bolus', function () {
        var glucose_status = {"delta":-1,"glucose":160,"avgdelta":-1};
        var iob_data = {"iob":7.0,"activity":0.03,"bolussnooze":5.0,"basaliob":2};
        var meal_data = {"carbs":120,"boluses":6, "mealCOB":80};
        var currenttemp = {"duration":15,"rate":2.5,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        //output.rate.should.equal(0);
        //output.duration.should.equal(0);
    });

    it('should not set temp when boluses + basal IOB cover meal carbs', function () {
        var glucose_status = {"delta":1,"glucose":160,"avgdelta":1};
        var iob_data = {"iob":7.0,"activity":0.02,"bolussnooze":4.0,"basaliob":3};
        var meal_data = {"carbs":120,"boluses":11, "mealCOB":80};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        console.log(output);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        //(typeof output.rate).should.equal('undefined');
        //(typeof output.duration).should.equal('undefined');
    });

    it('should not set temp when boluses + basal IOB cover meal carbs', function () {
        var meal_data = {"carbs":15,"boluses":2, "mealCOB":15}
        var glucose_status = {"delta":3,"glucose":200,"avgdelta":8.667}
        var currenttemp = {"duration":3,"rate":3.5,"temp":"absolute"}
        var iob_data = {"iob":2.701,"activity":0.0107,"bolussnooze":0.866,"basaliob":1.013,"netbasalinsulin":1.1,"hightempinsulin":1.8}
        var profile_data = {"max_iob":3,"type":"current","dia":3,"current_basal":0.9,"max_daily_basal":1.3,"max_basal":3.5,"min_bg":105,"max_bg":105,"sens":40,"carb_ratio":10}
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0.9);
        //output.duration.should.equal(30);
        //(typeof output.rate).should.equal('undefined');
        //(typeof output.duration).should.equal('undefined');
    });
    */

    it('should temp to zero with double sensitivity adjustment', function () {
        //var glucose_status = {"delta":1,"glucose":160,"avgdelta":1};
        var iob_data = {"iob":0.5,"activity":0.001,"bolussnooze":0.0,"basaliob":0.5};
        var autosens_data = {"ratio":0.5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens_data, meal_data, tempBasalFunctions);
        //console.log(output);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
    });

    it('maxSafeBasal current_basal_safety_multiplier of 1 should cause the current rate to be set, even if higher is needed', function () {
        var glucose_status = {"delta":5,"glucose":185,"long_avgdelta":5,"short_avgdelta":5};
        var iob_data = {"iob":0,"activity":-0.01,"bolussnooze":0};
        profile.current_basal_safety_multiplier = 1;
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(0.9);
        output.reason.should.match(/.*, adj. req. rate:.* to maxSafeBasal:.*, no temp, setting/);
    });

    it('maxSafeBasal max_daily_safety_multiplier of 1 should cause the max daily rate to be set, even if higher is needed', function () {
        var glucose_status = {"delta":5,"glucose":185,"long_avgdelta":5,"short_avgdelta":5};
        var iob_data = {"iob":0,"activity":-0.01,"bolussnooze":0};
        profile.current_basal_safety_multiplier = null;
        profile.max_daily_safety_multiplier = 1;
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(1.3);
        output.reason.should.match(/.*, adj. req. rate:.* to maxSafeBasal:.*, no temp, setting/);
    });

    it('overriding maxSafeBasal multipliers to 10 should increase temp', function () {
        var glucose_status = {"delta":5,"glucose":285,"long_avgdelta":5,"short_avgdelta":5};
        var iob_data = {"iob":0,"activity":-0.01,"bolussnooze":0};
        profile.max_basal = 5;
        profile.current_basal_safety_multiplier = 10;
        profile.max_daily_safety_multiplier = 10;
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(5);
        output.reason.should.match(/.*, adj. req. rate:.* to maxSafeBasal:.*, no temp, setting/);
    });

    it('should round appropriately for small basals when setting basal to maxSafeBasal ', function () {
        var glucose_status = {"delta":5,"glucose":185,"long_avgdelta":5,"short_avgdelta":5};
	var profile2 = {"max_iob":2.5,"dia":3,"type":"current","current_basal":0.025,"max_daily_basal":1.3,"max_basal":.05,"max_bg":120,"min_bg":110,"sens":200,"model":"523"};
	var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile2, autosens, meal_data, tempBasalFunctions);
        output.rate.should.equal(0.05);
	output.duration.should.equal(30);
        output.reason.should.match(/.*, adj. req. rate:.* to maxSafeBasal: 0.05, no temp, setting 0.05/);
    });
    
    it('should match the basal rate precision available on a 523', function () {
        //var currenttemp = {"duration":30,"rate":0,"temp":"absolute"};
        var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
        profile.current_basal = 0.825;
        profile.model = "523";
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0);
        //output.duration.should.equal(0);
        output.rate.should.equal(0.825);
        output.duration.should.equal(30);
        output.reason.should.match(/in range.*/);
    });

    it('should match the basal rate precision available on a 522', function () {
        //var currenttemp = {"duration":30,"rate":0,"temp":"absolute"};
        var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
        profile.current_basal = 0.875;
        profile.model = "522";
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, autosens, meal_data, tempBasalFunctions);
        //console.log(output);
        //output.rate.should.equal(0);
        //output.duration.should.equal(0);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        output.reason.should.match(/in range.*/);
    });

});
