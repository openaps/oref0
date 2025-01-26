'use strict';

require('should');
var _ = require('lodash');
var carb_ratios = require('../lib/profile/carbs');

describe('Carb Ratio Profile', function() {
    var carbratio_input = {
        units: 'grams',
        schedule: [
            { offset: 0, ratio: 15, start: '00:00:00' },
            { offset: 180, ratio: 18, start: '03:00:00' },
            { offset: 360, ratio: 20, start: '06:00:00' }
        ]
    };

    it('should return current carb ratio from schedule', function() {
        var now = new Date('2025-01-26T02:00:00');
        var ratio = carb_ratios.carbRatioLookup(null, {carbratio: carbratio_input}, null, now);
        ratio.should.equal(15);
    });

    it('should handle ratio schedule changes', function() {
        var now = new Date('2025-01-26T04:00:00');
        var ratio = carb_ratios.carbRatioLookup(null, {carbratio: carbratio_input}, null, now);
        ratio.should.equal(18);
    });

    it('should handle exchanges unit conversion', function() {
        var exchange_input = {
            units: 'exchanges',
            schedule: [
                { offset: 0, ratio: 12, start: '00:00:00' }
            ]
        };
	var now = new Date('2025-01-26T04:00:00');
        var ratio = carb_ratios.carbRatioLookup(null, {carbratio: exchange_input}, null, now);
        ratio.should.equal(1); // 12 grams per exchange
    });

    it('should reject invalid ratios', function() {
        var invalid_input = {
            units: 'grams',
            schedule: [
                { offset: 0, ratio: 2, start: '00:00:00' } // Less than min of 3
            ]
        };

	var final_result = {
	    stdout: ''
	    , err: ''
	    , return_val : 0
	};
	
        var ratio = carb_ratios.carbRatioLookup(final_result, {carbratio: invalid_input});
        should.not.exist(ratio);
    });
});
