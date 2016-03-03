'use strict';

require('should');


describe('getLastGlucose', function ( ) {
    var getLastGlucose = require('../lib/glucose-get-last.js');
	
	it('should return error if no glucose data is present', function () {
		var glucose_status = getLastGlucose({});
		glucose_status.isFailure.should.be.ok;
		glucose_status.reasonHint.should.be.type('string');
	});
	it('should not return valid result if there is only one reading', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime(),
				glucose: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.isFailure.should.not.be.ok;
		glucose_status.isValid.should.not.be.ok;
		glucose_status.reasonHint.should.be.type('string');
	});	

	it('should not return valid result if the last bg is too old', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (15 * 60 * 1000),
				glucose: 100
			},
			{
				date: now.getTime() - (20 * 60 * 1000),
				glucose: 100
			},
			{
			date: now.getTime() - (25 * 60 * 1000),
				glucose: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.isFailure.should.not.be.ok;
		glucose_status.isValid.should.not.be.ok;
		glucose_status.reasonHint.should.be.type('string');
	});

	it('should not return valid result if we dont have at least 3 readings', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (5 * 60 * 1000),
				glucose: 100
			},
			{
				date: now.getTime() - (10 * 60 * 1000),
				glucose: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.isFailure.should.not.be.ok;
		glucose_status.isValid.should.not.be.ok;
		glucose_status.reasonHint.should.be.type('string');
	});
	
	it('should not return valid result if the second reading is too old', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (5 * 60 * 1000),
				glucose: 100
			}
			, {
				date: now.getTime() - (60 * 60 * 1000),
				glucose: 100
			}
			, {
				date: now.getTime() - (65 * 60 * 1000),
				glucose: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.isFailure.should.not.be.ok;
		glucose_status.isValid.should.not.be.ok;
		glucose_status.reasonHint.should.be.type('string');
	});
	
	
	it('should return a valid result even on 3 readings', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (5 * 60 * 1000),
				glucose: 100
			}
			, {
				date: now.getTime() - (10 * 60 * 1000),
				glucose: 100
			}
			, {
				date: now.getTime() - (15 * 60 * 1000),
				glucose: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.isFailure.should.not.be.ok;
		glucose_status.isValid.should.be.ok;
		glucose_status.glucose.should.be.equal(100);
	});

	it('should return a valid result even on readings got from NS', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (5 * 60 * 1000),
				sgv: 100
			}
			, {
				date: now.getTime() - (10 * 60 * 1000),
				sgv: 100
			}
			, {
				date: now.getTime() - (15 * 60 * 1000),
				sgv: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.isFailure.should.not.be.ok;
		glucose_status.isValid.should.be.ok;
		glucose_status.glucose.should.be.equal(100);
	});

	it('should return a valid result with a good extrapolated glucose level (linear)', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (5 * 60 * 1000),
				sgv: 110
			}
			, {
				date: now.getTime() - (10 * 60 * 1000),
				sgv: 105
			}
			, {
				date: now.getTime() - (15 * 60 * 1000),
				sgv: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.glucose.should.be.equal(115);
	});

	it('should return a good extrapolated glucose level (non-linear)', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (5 * 60 * 1000),
				sgv: 115
			}
			, {
				date: now.getTime() - (10 * 60 * 1000),
				sgv: 105
			}
			, {
				date: now.getTime() - (15 * 60 * 1000),
				sgv: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.glucose.should.be.equal(125);
	});

	it('should return a correct delta (non-linear)', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (5 * 60 * 1000),
				sgv: 115
			}
			, {
				date: now.getTime() - (10 * 60 * 1000),
				sgv: 105
			}
			, {
				date: now.getTime() - (15 * 60 * 1000),
				sgv: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.delta.should.be.equal(10);
	});

	it('should return a correct avgdelta', function () {
		var now = new Date();
		var sample_data = [
			{
				date: now.getTime() - (0 * 60 * 1000),
				sgv: 115
			}
			, {
				date: now.getTime() - (5 * 60 * 1000),
				sgv: 105
			}
			, {
				date: now.getTime() - (10 * 60 * 1000),
				sgv: 100
			}
		];
		var glucose_status = getLastGlucose(sample_data);
		glucose_status.avgdelta.should.be.equal(7.5);
	});


});