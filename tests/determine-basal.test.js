'use strict';

require('should');



describe('determine-basal', function ( ) {
    var determine_basal = require('../lib/determine-basal/determine-basal');
    var setTempBasal = require('../lib/basal-set-temp');

   //function determine_basal(glucose_status, currenttemp, iob_data, profile)

    // standard initial conditions for all determine-basal test cases unless overridden
    var glucose_status = {"delta":0,"glucose":115,"avgdelta":0};
    var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
    var iob_data = {"iob":0,"activity":0,"bolusiob":0};
    var profile = {"max_iob":1.5,"dia":3,"type":"current","current_basal":0.9,"max_daily_basal":1.3,"max_basal":3.5,"max_bg":120,"min_bg":110,"sens":40, "target_bg":110};

    it('should do nothing when in range w/o IOB', function () {
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/in range/);
    });

    it('should set current temp when in range w/o IOB with Offline set', function () {
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, 'Offline',setTempBasal);
        output.rate.should.equal(0.9);
        output.duration.should.equal(30);
        output.reason.should.match(/in range.*setting current basal/);
    });
    
    it('should cancel any temp when in range w/o IOB', function () {
        var currenttemp = {"duration":30,"rate":0,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/in range.*cancel/);
    });
    

    // low glucose suspend test cases
    it('should temp to 0 when low w/o IOB', function () {
        var glucose_status = {"delta":-5,"glucose":75,"avgdelta":-5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 75<80/);
    });

    it('should do nothing when low and rising w/o IOB', function () {
        var glucose_status = {"delta":5,"glucose":75,"avgdelta":5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/75<80.*no high-temp/);
    });

    it('should do nothing when low and rising w/ negative IOB', function () {
        var glucose_status = {"delta":5,"glucose":75,"avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/75<80.*no high-temp/);
    });

    it('should do nothing on uptick even if avgdelta is still negative', function () {
        var glucose_status = {"delta":1,"glucose":75,"avgdelta":-2};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/BG 75<80/);
    });

    it('should temp to 0 when rising slower than BGI', function () {
        var glucose_status = {"delta":1,"glucose":75,"avgdelta":1};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 75<80/);
    });

    it('should temp to 0 when low and falling, regardless of BGI', function () {
        var glucose_status = {"delta":-1,"glucose":75,"avgdelta":-1};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0.5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 75<80/);
    });

    it('should cancel high-temp when low and rising faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var glucose_status = {"delta":5,"glucose":75,"avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/BG 75<80, avg delta .*, cancel high temp/);
    });
    
    it('should cancel low-temp eventualBG is higher then max_bg', function () {
        var currenttemp = {"duration":20,"rate":0.9,"temp":"absolute"};
        var glucose_status = {"delta":5,"glucose":75,"avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/BG 75<80, avg delta .*, cancel low temp/);
    });

    it('should high-temp when > 80-ish and rising w/ lots of negative IOB', function () {
        var glucose_status = {"delta":5,"glucose":85,"avgdelta":5};
        var iob_data = {"iob":-1,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });
    
    it('should high-temp when > 180-ish and rising but not more then maxSafeBasal', function () {
        var glucose_status = {"delta":5,"glucose":185,"avgdelta":5};
        var iob_data = {"iob":0,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);

        output.reason.should.match(/max_iob .*, ajd. req. rate:.* to maxSafeBasal:.*,no temp, setting/);
    });
    
    it('should reduce high-temp when schedule would be above max', function () {
        var glucose_status = {"delta":5,"glucose":145,"avgdelta":5};
        var currenttemp = {"duration":160,"rate":1.9,"temp":"absolute"};
        var iob_data = {"iob":0,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.duration.should.equal(30);
        output.reason.should.match(/.*mins .* = .* > req .*/);
    });
    
    it('should continue high-temp when required ~= temp running', function () {
        var glucose_status = {"delta":5,"glucose":145,"avgdelta":5};
        var currenttemp = {"duration":30,"rate":3.1,"temp":"absolute"};
        var iob_data = {"iob":0,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/Eventual BG .*>.*, temp .* >~ req /);
    });
    
    it('should set high-temp when required running temp is low', function () {
        var glucose_status = {"delta":5,"glucose":145,"avgdelta":5};
        var currenttemp = {"duration":30,"rate":1.1,"temp":"absolute"};
        var iob_data = {"iob":0,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*>.*, temp/);
    });
    
    it('should stop high-temp when iob is near max_iob.', function () {
        var glucose_status = {"delta":5,"glucose":485,"avgdelta":5};
        var iob_data = {"iob":3.5,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/basal_iob .* > max_iob .*/);
    });

    it('should temp to 0 when LOW w/ positive IOB', function () {
        var glucose_status = {"delta":0,"glucose":39,"avgdelta":0};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0.5};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 39<80/);
    });

    it('should temp to 0 when LOW w/ negative IOB', function () {
        var glucose_status = {"delta":0,"glucose":39,"avgdelta":0};
        var iob_data = {"iob":-2.5,"activity":-0.03,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 39<80/);
    });

    it('should temp to 0 when LOW w/ no IOB', function () {
        var glucose_status = {"delta":0,"glucose":39,"avgdelta":0};
        var iob_data = {"iob":0,"activity":0,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(30);
        output.reason.should.match(/BG 39<80/);
    });
    


    // low eventualBG

    it('should low-temp when eventualBG < min_bg', function () {
        var glucose_status = {"delta":-3,"glucose":110,"avgdelta":-1};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.be.below(0.8);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*<110, no temp, setting .*/);
    });
    
    it('should do nothing when eventualBG < min_bg but low temp in progress', function () {
        var glucose_status = {"delta":-3,"glucose":110,"avgdelta":-1};
        var currenttemp = {"duration":20,"rate":0.0,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/Eventual BG .*<110, temp .*/);
    });

    it('should cancel low-temp when lowish and avg.delta rising faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":0.5,"temp":"absolute"};
        var glucose_status = {"delta":3,"glucose":85,"avgdelta":3};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/Eventual BG.*<.*but Avg. Delta.*> BGI.*; cancel/);
    });
    
    it('should cancel low-temp when lowish and delta rising faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":0.5,"temp":"absolute"};
        var glucose_status = {"delta":3,"glucose":85,"avgdelta":2};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/Eventual BG.*<.*but Delta.*> BGI.*; cancel/);
    });
    
    it('should do nothing when lowish and delta rising faster than BGI', function () {
        var currenttemp = {"duration":0,"rate":0.5,"temp":"absolute"};
        var glucose_status = {"delta":3,"glucose":85,"avgdelta":2};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.reason.should.match(/Eventual BG.*<.*but Delta.*> BGI.*; no temp to cancel/);
    });

    it('should low-temp when low and rising slower than BGI', function () {
        var glucose_status = {"delta":1,"glucose":85,"avgdelta":1};
        var iob_data = {"iob":-0.5,"activity":-0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.be.below(0.8);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });

    // high eventualBG

    it('should high-temp when eventualBG > max_bg', function () {
        var glucose_status = {"delta":+3,"glucose":120,"avgdelta":+1};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/Eventual BG .*>120/);
    });

    it('should cancel high-temp when high and avg. delta falling faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":175,"avgdelta":-5};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/Eventual BG.*>.*but Avg. Delta.*< BGI.*; cancel/);
    });
    
    it('should cancel high-temp when high and delta falling faster than BGI', function () {
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":175,"avgdelta":-4};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
        output.reason.should.match(/Eventual BG.*>.*but Delta.*< BGI.*; cancel/);
    });
    
    it('should do nothing when not temp and high and delta falling faster than BGI', function () {
        var currenttemp = {"duration":0,"rate":0,"temp":"absolute"};
        var glucose_status = {"delta":-5,"glucose":175,"avgdelta":-4};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
        output.reason.should.match(/Eventual BG.*>.*but Delta.*< BGI.*; no temp to cancel/);
    });

    it('should high-temp when high and falling slower than BGI', function () {
        var glucose_status = {"delta":-1,"glucose":175,"avgdelta":-1};
        var iob_data = {"iob":1,"activity":0.01,"bolusiob":0};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
        output.reason.should.match(/no temp, setting/);
    });


    it('should profile.current_basal be undefined return error', function () {
      var result = determine_basal(undefined,undefined,undefined,undefined);
      result.error.should.equal('Error: could not get current basal rate');
    }); 

    it('should bg be < 30 (Dexcom is in ???) return error', function () {
      var result = determine_basal({glucose:18},undefined, undefined, {"current_basal":0.0}, undefined,setTempBasal);
      result.error.should.equal('CGM is calibrating or in ??? state');
    });  

    it('profile should contain min_bg,max_bg or target_bg', function () {
      var result = determine_basal({glucose:100},undefined, undefined, {"current_basal":0.0}, undefined,setTempBasal);
      result.error.should.equal('Error: could not determine target_bg');
    }); 

    it('iob_data should not be undefined', function () {
      var result = determine_basal({glucose:100},undefined, undefined, {"current_basal":0.0, "target_bg":100}, undefined,setTempBasal);
      result.error.should.equal('Error: iob_data undefined');
    }); 

    it('iob_data should contain activity, iob, bolusiob', function () {
      var result = determine_basal({glucose:100}, undefined,{"activity":0}, {"current_basal":0.0, "target_bg":100}, undefined,setTempBasal);
      result.error.should.equal('Error: iob_data missing some property');
    });  

    it('should return error eventualBG if something went wrong', function () {
      var result = determine_basal({glucose:100}, undefined,{"activity":0, "iob":0,"bolusiob":0}, {"current_basal":0.0, "target_bg":100, "sens":NaN}, undefined,setTempBasal);
      result.error.should.equal('Error: could not calculate eventualBG');
    });

    // meal assist / bolus snooze
    // right after 20g 1U meal bolus
    it('should do nothing when low and rising after meal bolus', function () {
        var glucose_status = {"delta":1,"glucose":80,"avgdelta":1};
        var iob_data = {"iob":0.5,"activity":-0.01,"bolusiob":1};
        var meal_data = {"dia_carbs":20,"dia_bolused":1};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        (typeof output.rate).should.equal('undefined');
        (typeof output.duration).should.equal('undefined');
    });
    
    it('should cancel high temp when low and dropping after meal bolus', function () {
        var glucose_status = {"delta":-1,"glucose":80,"avgdelta":1};
        var iob_data = {"iob":0.5,"activity":-0.01,"bolusiob":1};
        var currenttemp = {"duration":20,"rate":2,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
    });
    
    it('should cancel low temp when low and rising after meal bolus', function () {
        var glucose_status = {"delta":1,"glucose":80,"avgdelta":1};
        var iob_data = {"iob":0.5,"activity":-0.01,"bolusiob":1};
        var currenttemp = {"duration":20,"rate":0,"temp":"absolute"};
        var output = determine_basal(glucose_status, currenttemp, iob_data, profile, undefined,setTempBasal);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
    });

    // 40m after 20g 1U meal bolus
    it('should high-temp aggressively when 120 and rising after meal bolus', function () {
        var glucose_status = {"delta":10,"glucose":120,"avgdelta":10};
        var iob_data = {"iob":0.4,"activity":0,"bolusiob":0.7};
        var meal_data = {"dia_carbs":20,"dia_bolused":1};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(1.8);
        output.duration.should.equal(30);
    });

    // 60m after 20g 1U meal bolus
    it('should high-temp aggressively when 150 and rising after meal bolus', function () {
        var glucose_status = {"delta":3,"glucose":150,"avgdelta":5};
        var iob_data = {"iob":0.5,"activity":0.01,"bolusiob":0.6};
        var meal_data = {"dia_carbs":20,"dia_bolused":1};
        var currenttemp = {"duration":10,"rate":2,"temp":"absolute"};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(2.2);
        output.duration.should.equal(30);
    });

    // 75m after 20g 1U meal bolus
    it('should cancel high-temp when 160 and dropping after meal bolus', function () {
        var glucose_status = {"delta":-3,"glucose":160,"avgdelta":0};
        var iob_data = {"iob":0.9,"activity":0.02,"bolusiob":0.5};
        var meal_data = {"dia_carbs":20,"dia_bolused":1};
        var currenttemp = {"duration":15,"rate":2.5,"temp":"absolute"};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
    });

    // right after 120g 6U meal bolus
    it('should high-temp when 120 and rising after meal bolus', function () {
        var glucose_status = {"delta":1,"glucose":120,"avgdelta":1};
        var iob_data = {"iob":6,"activity":0,"bolusiob":6};
        var meal_data = {"dia_carbs":120,"dia_bolused":6};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
    });

    // after 120g 6U meal bolus
    it('should high-temp when 140 and rising after meal bolus', function () {
        var glucose_status = {"delta":1,"glucose":140,"avgdelta":1};
        //TODO: figure out how to track basal_iob vs. net_iob
        var iob_data = {"iob":6.5,"activity":0.01,"bolusiob":5.5};
        var meal_data = {"dia_carbs":120,"dia_bolused":6};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
    });

    // after 120g 6U meal bolus
    it('should high-temp when 160 and rising after meal bolus', function () {
        var glucose_status = {"delta":1,"glucose":160,"avgdelta":1};
        //TODO: figure out how to track basal_iob vs. net_iob
        var iob_data = {"iob":7.0,"activity":0.02,"bolusiob":5};
        var meal_data = {"dia_carbs":120,"dia_bolused":6};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.be.above(1);
        output.duration.should.equal(30);
    });

    // after 120g 6U meal bolus
    it('should cancel temp when 160 and falling after meal bolus', function () {
        var glucose_status = {"delta":-1,"glucose":160,"avgdelta":-1};
        //TODO: figure out how to track basal_iob vs. net_iob
        var iob_data = {"iob":7.0,"activity":0.03,"bolusiob":5};
        var meal_data = {"dia_carbs":120,"dia_bolused":6};
        var currenttemp = {"duration":15,"rate":2.5,"temp":"absolute"};
        var output = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile);
        output.rate.should.equal(0);
        output.duration.should.equal(0);
    });

});
