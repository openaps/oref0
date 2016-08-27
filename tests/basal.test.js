'use strict';

require('should');

var moment = require('moment');

describe('Basal', function ( ) {

 it('should find the right max basal', function() {

    var basalprofile = [{'i': 0, 'start': '00:00:00', 'rate': 0, 'minutes': 0},
        {'i': 1, 'start': '00:15:00', 'rate': 2, 'minutes': 15 },
        {'i': 1, 'start': '00:45:00', 'rate': 0.5, 'minutes': 45 }];

	var inputs = {'basals': basalprofile}

	var basal = require('../lib/profile/basal');
	
	console.log(basal);
	
	var maxBasal = basal.maxDailyBasal(inputs);
	
	console.log(maxBasal);
	
	maxBasal.should.equal(2);
	
  });



});
