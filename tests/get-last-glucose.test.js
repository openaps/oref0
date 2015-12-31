'use strict';

require('should');


describe('getLastGlucose', function ( ) {
    var getLastGlucose = require('../lib/glucose-get-last.js');
    
    it('should handle NS sgv fields', function () {
      var glucose_status = getLastGlucose([{sgv: 100}, {sgv: 95}, {sgv: 90}, {sgv: 70}]);
      glucose_status.delta.should.equal(5);
      glucose_status.glucose.should.equal(100);
      glucose_status.avgdelta.should.equal(10);
    });
});