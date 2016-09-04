'use strict';

require('should');

var moment = require('moment');

describe('Basal', function ( ) {

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 0, 'minutes': 0},
        {'i': 1, 'start': '00:15:00', 'rate': 2, 'minutes': 15 },
        {'i': 1, 'start': '00:45:00', 'rate': 0.5, 'minutes': 45 }];

 it('should find the right max daily basal', function() {

    var inputs = {'basals': basalprofile};
    var basal = require('../lib/profile/basal');
    var maxBasal = basal.maxDailyBasal(inputs);
    maxBasal.should.equal(2);

  });


 it('should find the right basal for a given moment', function() {

    var inputs = {'basals': basalprofile};
    var startingPoint = new Date(moment('2016-06-13 00:20:00.000').format());
    var startingPoint2 = new Date(moment('2016-06-13 01:00:00.000').format());
    var basal = require('../lib/profile/basal');
    var b = basal.basalLookup(basalprofile,startingPoint);
    b.should.equal(2);
    b = basal.basalLookup(basalprofile,startingPoint2);
    b.should.equal(0.5);

  });

});
