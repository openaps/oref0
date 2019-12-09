'use strict';

require('should');


describe('getLastGlucose', function ( ) {
    var getLastGlucose = require('../lib/glucose-get-last.js');
    
    it('should handle NS sgv fields', function () {
      var glucose_status = getLastGlucose([{date: 1467942845000, sgv: 100}, {date: 1467942544500, sgv: 95}, {date: 1467942244000, sgv: 85}, {date: 1467941944000, sgv: 70}]);
      //console.log(glucose_status);
      glucose_status.delta.should.equal(5);
      glucose_status.glucose.should.equal(100);
      glucose_status.short_avgdelta.should.equal(7.5);
      glucose_status.long_avgdelta.should.equal(0);
    });
    it('should handle two receivers 30s and 3 mg/dL offset', function () {
      var glucose_status = getLastGlucose([{date: 1467942875000, sgv: 103}, {date: 1467942845000, sgv: 100}, {date: 1467942574500, sgv: 98}, {date: 1467942544500, sgv: 95}, {date: 1467942274000, sgv: 88}, {date: 1467942244000, sgv: 85}, {date: 1467941974000, sgv: 73}, {date: 1467941944000, sgv: 70}]);
      //console.log(glucose_status);
      glucose_status.delta.should.equal(5);
      glucose_status.glucose.should.equal(101.5);
      glucose_status.short_avgdelta.should.equal(7.5);
      glucose_status.long_avgdelta.should.equal(0);
    });
    it('should handle fields named glucose and calculate long_avgdelta', function () {
      var glucose_status = getLastGlucose([{"date": 1469509700000, "glucose": 97}, {"date": 1469509400000, "glucose": 94}, {"date": 1469509100000, "glucose": 87}, {"date": 1469508800000, "glucose": 81}, {"date": 1469508500000, "glucose": 78}, {"date": 1469508200000, "glucose": 78}, {"date": 1469507900000, "glucose": 81}, {"date": 1469507600000, "glucose": 84}, {"date": 1469507300000, "glucose": 87}, {"date": 1469507000000, "glucose": 93}, {"date": 1469506700000, "glucose": 102}, {"date": 1469506400000, "glucose": 104}, {"date": 1469506100000, "glucose": 99}, {"date": 1469505800000, "glucose": 81}, {"date": 1469505500000, "glucose": 76}, {date: 1469509700000, glucose: 97}]);
      //console.log(glucose_status);
      glucose_status.delta.should.equal(3);
      glucose_status.glucose.should.equal(97);
      glucose_status.short_avgdelta.should.equal(4.44);
      glucose_status.long_avgdelta.should.equal(2.86);
    });
    it('should fall back to dateString property', function () {
      var glucose_status = getLastGlucose([{dateString: "2019-12-04T08:54:19.288-0800", sgv: 100}, {date: 1467942544500, sgv: 95}, {date: 1467942244000, sgv: 85}, {date: 1467941944000, sgv: 70}]);
      glucose_status.date.should.equal(1575478459288);
    });
    it('should skip meter BG', function () {
      var glucose_status = getLastGlucose([{date: 1467942845000, glucose: null, mbg: 100}, {date: 1467942544500, sgv: 95}, {date: 1467942244000, sgv: 85}, {date: 1467941944000, sgv: 70}]);
      //console.log(glucose_status);
      glucose_status.delta.should.equal(10);
      glucose_status.glucose.should.equal(95);
      glucose_status.short_avgdelta.should.equal(11.25);
      glucose_status.long_avgdelta.should.equal(0);
    });
});
