'use strict';

var should = require('should');
var withRawGlucose = require('../lib/with-raw-glucose');

var cals = [{
  scale: 1
  , intercept: 25717.82377004309
  , slope: 766.895601715918
}];

describe('IOB', function ( ) {
  it('should add raw glucose and not mess with real glucose', function ( ) {
    var entry = {unfiltered: 113680, filtered: 111232, glucose: 110, noise: 1};
    withRawGlucose(entry, cals);

    entry.glucose.should.equal(110);
    entry.raw.should.equal(113);
    entry.noise.should.equal(1);
  });

  it('should add raw glucose and not mess with sgv from NS', function ( ) {
    var entry = {unfiltered: 113680, filtered: 111232, sgv: 110, noise: 1};
    withRawGlucose(entry, cals);

    should.not.exist(entry.glucose);
    entry.sgv.should.equal(110);
    entry.raw.should.equal(113);
    entry.noise.should.equal(1);
  });

  it('should add raw glucose and set missing glucose', function ( ) {
    var entry = {unfiltered: 113680, filtered: 111232, noise: 1};
    withRawGlucose(entry, cals);

    entry.glucose.should.equal(115);
    entry.raw.should.equal(115);
    entry.noise.should.equal(2);
  });

  it('should add raw glucose, but set set noise to 3 when glucose above maxRaw', function ( ) {
    var entry = {unfiltered: 143680, filtered: 141232, noise: 1};
    withRawGlucose(entry, cals, 150);

    //should.not.exist(entry.glucose);
    entry.raw.should.equal(154);
    entry.noise.should.equal(3);
  });

  it('should add raw glucose, and set missing glucose when maxRaw is higher', function ( ) {
    var entry = {unfiltered: 143680, filtered: 141232, noise: 1};
    withRawGlucose(entry, cals, 250);

    entry.glucose.should.equal(154);
    entry.raw.should.equal(154);
    entry.noise.should.equal(2);
  });

});
