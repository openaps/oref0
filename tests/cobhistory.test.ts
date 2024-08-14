import find_cob_iob_entries from '../lib/meal/history'
import { PumpHistoryEvent } from '../lib/types/PumpHistoryEvent';

describe('cobhistory', function ( ) {
    // @todo: test clock skew (the code accept a tollerance of ±2 seconds, or maybe 1,9999?)
	var pumpHistory: PumpHistoryEvent[] = [
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
        var inputs = {
            history: pumpHistory,
            carbs: carbHistory,
            profile: {}
        };

        var output = find_cob_iob_entries(inputs);

        //console.log(output);

        // BolusWizard carb_input without a timestamp-matched Bolus will be ignored
        expect(output.length).toStrictEqual(6)
    });

});
