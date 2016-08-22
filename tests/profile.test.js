'use strict';

require('should');
var _ = require('lodash');

describe('Profile', function ( ) {

    var baseInputs = {
        settings: {
            insulin_action_curve: 3
        }
        , basals: [
            {minutes: 0, rate: 1}
        ]
        , targets: {
            targets: [
                { offset: 0, high: 120, low: 100 }
            ]
        }
        , temptargets: [
        ]
        , isf: {
            sensitivities: [
                { offset: 0, i: 0, x: 0, start: '00:00:00', sensitivity: 100 }
            ]
        }
        , carbratio: {
            units: 'grams'
            , schedule: [
                { offset: 0, ratio: 20 }
            ]
        }
    };

    it('should should create a profile from inputs', function () {
        var profile = require('../lib/profile')(baseInputs);
        profile.max_iob.should.equal(0);
        profile.dia.should.equal(3);
        profile.sens.should.equal(100);
        profile.current_basal.should.equal(1);
        profile.max_bg.should.equal(120);
        profile.min_bg.should.equal(100);
        profile.carb_ratio.should.equal(20);
    });

    it('should adjust carbratio with carbratio_adjustmentratio', function () {

        var profile = require('../lib/profile')(baseInputs);
        profile.carb_ratio.should.equal(20);

        var profileA = require('../lib/profile')(_.merge({}, baseInputs, {
            carbratio_adjustmentratio: .8
        }));
        profileA.carb_ratio.should.equal(16);

    });

});
