'use strict';

var should = require('should');
var _ = require('lodash');

describe('cobhistory', function() {
    var total_cob = require('../lib/meal/total');

    var ph = [{
        "_type": "Rewind",
        "timestamp": "2016-06-19T10:59:36+03:00"
    },
        {
            "_type": "Bolus",
            "timestamp": "2016-06-19T12:59:36+03:00",
            "amount": 5,
            "bolus": 5}];

    var treatments = [{
            "_type": "BolusWizard",
            "timestamp": "2016-06-19T12:59:36+03:00",
            "carbs": 40
        },
        {
            "_type": "Bolus",
            "timestamp": "2016-06-19T12:59:36+03:00",
            "amount": 5,
            "bolus": 5
        }
    ];


    //function determine_basal(glucose_status, currenttemp, iob_data, profile)

    it('should dedupe entries', function() {
        var inputs = {};
        inputs.pumphistory = ph;
        inputs.treatments = treatments;

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        inputs.basalprofile = basalprofile;

        inputs.profile = {
            dia: 6,
            unit_test: true,
            bolussnooze_dia_divisor: 2,
            basalprofile: basalprofile,
            current_basal: 1,
            carb_ratio: 10,
            sens: 5,
            maxCOB: 100,
            max_daily_basal: 5,
            autosens_max: 1.15,
            autosens_min: 0.85,
            carb_ratios: {
                units: "grams",
                first: 1,
                schedule: [{
                    "q": 0,
                    "start": "00:00:00",
                    "r": 140,
                    "ratio": 10,
                    "offset": 0,
                    "i": 0,
                    "x": 0
                }]
            },
            min_5m_carbimpact: 5,
            isfProfile: {
                units: "mg/dL",
                user_preferred_units: "mmol/L",
                sensitivities: [{
                    "i": 0,
                    "start": "00:00:00",
                    "sensitivity": 115,
                    "x": 0,
                    "offset": 0
                }],
                "first": 2
            }
        };

        var startTime = new Date("2016-06-19T12:00:36+03:00");
        var time = new Date("2016-06-19T12:59:36+03:00");
        var glucose = [];

        for (var i = 0; i < 13; i++) {
            var entry = {};
            var d = new Date(startTime.getTime() + (i * 5 * 60 * 1000));
            entry.dateString = d.toISOString();
            entry.date = d.getTime();
            entry.sgv = 100 + i * 5;
            glucose.push(entry);
        }

        inputs.glucose = glucose;

        var output = total_cob(_.cloneDeep(inputs), time);

        console.log(output);
        output.mealCOB.should.equal(40);

        time = new Date("2016-06-19T13:59:36+03:00");
        glucose = [];

        for (var i = 0; i < 24; i++) {
            var entry = {};
            var d = new Date(startTime.getTime() + (i * 5 * 60 * 1000));
            entry.dateString = d.toISOString();
            entry.date = d.getTime();
            entry.sgv = 100 + i * 10;
            glucose.push(entry);
        }

        inputs.glucose = glucose;

        var output = total_cob(_.cloneDeep(inputs), time);
        console.log(output);

        output.mealCOB.should.be.lessThan(31);

    });

});