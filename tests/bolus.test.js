'use strict';

var should = require('should');

describe('bolus', function () {
    var bolushistory = [
        {
            "_type": "Bolus",
            "_description": "Bolus 2017-04-12T12:49:49 head[4], body[0] op[0x01]",
            "timestamp": "2017-04-12T12:49:49-05:00",
            "_body": "",
            "programmed": 3.0,
            "_head": "011e1e00",
            "amount": 3.0,
            "duration": 0,
            "type": "normal",
            "_date": "71314c0c11"
        },
        {
            "_type": "Bolus",
            "_description": "Bolus 2017-04-12T12:47:53 head[4], body[0] op[0x01]",
            "timestamp": "2017-04-12T12:47:53-05:00",
            "_body": "",
            "programmed": 0.2,
            "_head": "01020200",
            "amount": 0.2,
            "duration": 0,
            "type": "normal",
            "_date": "752f4c4c11"
        }
    ];
    it('should not skip closely-timed boluses', function () {
        var reduce_boluses = require('../lib/bolus');
        var vals = reduce_boluses(bolushistory);
        vals.length.should.equal(1);
        vals[0].insulin.should.equal('3.2');
    })
});