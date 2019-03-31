'use strict';

var should = require('should');

describe('cobhistory', function ( ) {
    var find_cob_iob_entries = require('../lib/meal/history');

	var pumpHistory = [
		{"_type": "BolusWizard","timestamp": "2016-06-19T12:51:36-04:00","carb_input": 40},
		{"_type": "Bolus","timestamp": "2016-06-19T12:52:36-04:00","amount": 4.4}, 
		{"_type": "BolusWizard","timestamp": "2016-06-19T12:57:36-04:00","carb_input": 40},
		{"_type": "Bolus","timestamp": "2016-06-19T12:57:36-04:00","amount": 4.4}, 
		{"_type": "Bolus","timestamp": "2016-06-19T15:33:42-04:00","amount": 1.5},
		
		{"_type": "BolusWizard","timestamp": "2016-06-19T12:59:36-04:00","carb_input": 40},
		{"_type": "Bolus","timestamp": "2016-06-19T12:59:36-04:00","amount": 4.4},
		{"_type": "BolusWizard","timestamp": "2016-06-19T12:59:36-04:00","carb_input": 40},
		{"_type": "Bolus","timestamp": "2016-06-19T12:59:36-04:00","amount": 4.4}
		];
		
	var carbHistory = [
			{"_type": "BolusWizard","created_at": "2016-06-19T12:59:36-04:00","carbs": 40},
			{"_type": "Bolus","created_at": "2016-06-19T12:59:36-04:00","amount": 4.4},
			{"_type": "BolusWizard","created_at": "2016-06-19T12:59:36-04:00","carbs": 40},
			{"_type": "Bolus","created_at": "2016-06-19T12:59:36-04:00","amount": 4.4}
		];

   //function determine_basal(glucose_status, currenttemp, iob_data, profile)

    it('should dedupe entries', function () {
        var inputs = {};
        inputs.history = pumpHistory;
        inputs.carbs = carbHistory;
        inputs.profile = {};

        var output = find_cob_iob_entries(inputs);

        console.log(output);

        // BolusWizard carb_input without a timestamp-matched Bolus will be ignored
        output.length.should.equal(6);
    });

});
