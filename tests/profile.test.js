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
                { offset: 0, sensitivity: 100 }
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
        profile.max_bg.should.equal(100);
        profile.min_bg.should.equal(100);
        profile.carb_ratio.should.equal(20);
    });


    var currentTime = new Date();
    var creationDate = new Date(currentTime.getTime() - (5 * 60 * 1000));

    it('should create a profile with temptarget set', function() {
        var profile = require('../lib/profile')(_.merge({}, baseInputs, { temptargets: [{'eventType':'Temporary Target', 'reason':'Eating Soon', 'targetTop':80, 'targetBottom':80, 'duration':20, 'created_at': creationDate}]}));
        profile.max_iob.should.equal(0);
        profile.dia.should.equal(3);
        profile.sens.should.equal(100);
        profile.current_basal.should.equal(1);
        profile.max_bg.should.equal(80);
        profile.min_bg.should.equal(80);
        profile.carb_ratio.should.equal(20);
        profile.temptargetSet.should.equal(true);
    });


    var pastDate = new Date(currentTime.getTime() - 90*60*1000);
    it('should create a profile ignoring an out of date temptarget', function() {
        var profile = require('../lib/profile')(_.merge({}, baseInputs, { temptargets: [{'eventType':'Temporary Target', 'reason':'Eating Soon', 'targetTop':80, 'targetBottom':80, 'duration':20, 'created_at': pastDate}]}));
        profile.max_iob.should.equal(0);
        profile.dia.should.equal(3);
        profile.sens.should.equal(100);
        profile.current_basal.should.equal(1);
        profile.max_bg.should.equal(100);
        profile.min_bg.should.equal(100);
        profile.carb_ratio.should.equal(20);
    });

    it('should create a profile ignoring a temptarget with 0 duration', function() {
        var profile = require('../lib/profile')(_.merge({}, baseInputs, { temptargets: [{'eventType':'Temporary Target', 'reason':'Eating Soon', 'targetTop':80, 'targetBottom':80, 'duration':0, 'created_at': creationDate}]}));
        profile.max_iob.should.equal(0);
        profile.dia.should.equal(3);
        profile.sens.should.equal(100);
        profile.current_basal.should.equal(1);
        profile.max_bg.should.equal(100);
        profile.min_bg.should.equal(100);
        profile.carb_ratio.should.equal(20);
    });


    it('should error with invalid DIA', function () {
        var profile = require('../lib/profile')(_.merge({}, baseInputs, {settings: {insulin_action_curve: 1}}));
        profile.should.equal(-1);
    });

    it('should error with a current basal of 0', function () {
        var profile = require('../lib/profile')(_.merge({}, baseInputs, {basals: [{minutes: 0, rate: 0}]}));
        profile.should.equal(-1);
    });


    it('should set the profile model from input', function () {
        var profile = require('../lib/profile')(_.merge({}, baseInputs, {model: 554}));
        profile.model.should.equal(554);
    });


});
