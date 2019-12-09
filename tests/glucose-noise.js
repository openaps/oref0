'use strict';

require('should');

var moment = require('moment');
var stats = require('../lib/calc-glucose-stats');

describe('NOISE', function() {
  it('should calculate Clean Sensor Noise', () => {
    const glucoseHist = [{
      status: 0,
      state: 7,
      readDate: 1528890389945,
      readDateMills: 1528890389945,
      filtered: 161056,
      unfiltered: 158400,
      glucose: 155,
      trend: -3.9982585362819747,
    }, {
      status: 0,
      state: 7,
      readDate: 1528890689766,
      readDateMills: 1528890689766,
      filtered: 159360,
      unfiltered: 156544,
      glucose: 153,
      trend: -3.9992534726850986,
    }, {
      status: 0,
      state: 7,
      readDate: 1528890989467,
      readDateMills: 1528890989467,
      filtered: 157504,
      unfiltered: 154432,
      glucose: 150,
      trend: -4.667973699302471,
    }, {
      status: 0,
      state: 7,
      readDate: 1528891289963,
      readDateMills: 1528891289963,
      filtered: 155488,
      unfiltered: 151872,
      glucose: 147,
      trend: -5.3332266687999565,
    }, {
      status: 0,
      state: 7,
      readDate: 1528891589664,
      readDateMills: 1528891589664,
      filtered: 153312,
      unfiltered: 149984,
      glucose: 145,
      trend: -5.333937846289246,
    }, {
      status: 0,
      state: 7,
      readDate: 1528891889576,
      readDateMills: 1528891889576,
      filtered: 151008,
      unfiltered: 147264,
      glucose: 141,
      trend: -5.999273421330083,
    }, {
      status: 0,
      state: 7,
      readDate: 1528892189592,
      readDateMills: 1528892189592,
      filtered: 148544,
      unfiltered: 144256,
      glucose: 138,
      trend: -6.002474353316756,
    }];

    const currSGV = {
      status: 0,
      state: 7,
      readDate: 1528892489488,
      readDateMills: 1528892489488,
      filtered: 145920,
      unfiltered: 141632,
      glucose: 134,
      trend: -7.334767687903413,
    };

    glucoseHist.push(currSGV);

    var options = {
      glucose_hist: glucoseHist
    };

    const newHist = stats.updateGlucoseStats(options);

    newHist[0].noise.should.equal(1);
  });

  it('should calculate Medium Sensor Noise', () => {
    const glucoseHist = [{
      status: 0,
      state: 7,
      readDate: 1528890389945,
      readDateMills: 1528890389945,
      filtered: 161056,
      unfiltered: 158400,
      glucose: 155,
      trend: -3.9982585362819747,
    }, {
      status: 0,
      state: 7,
      readDate: 1528890689766,
      readDateMills: 1528890689766,
      filtered: 159360,
      unfiltered: 156544,
      glucose: 153,
      trend: -3.9992534726850986,
    }, {
      status: 0,
      state: 7,
      readDate: 1528890989467,
      readDateMills: 1528890989467,
      filtered: 157504,
      unfiltered: 154432,
      glucose: 150,
      trend: -4.667973699302471,
    }, {
      status: 0,
      state: 7,
      readDate: 1528891289963,
      readDateMills: 1528891289963,
      filtered: 155488,
      unfiltered: 151872,
      glucose: 147,
      trend: -5.3332266687999565,
    }, {
      status: 0,
      state: 7,
      readDate: 1528891589664,
      readDateMills: 1528891589664,
      filtered: 153312,
      unfiltered: 149984,
      glucose: 145,
      trend: -5.333937846289246,
    }, {
      status: 0,
      state: 7,
      readDate: 1528891889576,
      readDateMills: 1528891889576,
      filtered: 151008,
      unfiltered: 147264,
      glucose: 141,
      trend: -5.999273421330083,
    }, {
      status: 0,
      state: 7,
      readDate: 1528892189592,
      readDateMills: 1528892189592,
      filtered: 148544,
      unfiltered: 144256,
      glucose: 148,
      trend: -6.002474353316756,
    }];

    const currSGV = {
      status: 0,
      state: 7,
      readDate: 1528892489488,
      readDateMills: 1528892489488,
      filtered: 145920,
      unfiltered: 141632,
      glucose: 134,
      trend: -7.334767687903413,
    };

    glucoseHist.push(currSGV);

    var options = {
      glucose_hist: glucoseHist
    };

    const newHist = stats.updateGlucoseStats(options);

    newHist[0].noise.should.equal(3);
  });
});

