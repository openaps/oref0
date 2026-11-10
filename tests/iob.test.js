'use strict';

require('should');

var moment = require('moment');
var iob = require('../lib/iob');

describe('IOB', function() {

    it('should calculate IOB', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 2,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 3,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1
                }

            };

        var rightAfterBolus = iob(inputs)[0];
        rightAfterBolus.iob.should.equal(2);
        //rightAfterBolus.bolussnooze.should.equal(2);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(1.45);
        //hourLater.bolussnooze.should.be.lessThan(.5);
        hourLater.iob.should.be.greaterThan(0);
        hourLater.activity.should.be.greaterThan(0.01);
        hourLater.activity.should.be.lessThan(0.02);

        var afterDIAInputs = inputs;
        afterDIAInputs.clock = new Date(now + (3 * 60 * 60 * 1000)).toISOString();
        var afterDIA = iob(afterDIAInputs)[0];

        afterDIA.iob.should.equal(0);
        //afterDIA.bolussnooze.should.equal(0);
    });

    it('should calculate IOB with Ultra-fast curve', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 2,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 5,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1,
                    curve: 'ultra-rapid'
                }
            };

        var rightAfterBolus = iob(inputs)[0];

        rightAfterBolus.iob.should.equal(2);
        //rightAfterBolus.bolussnooze.should.equal(2);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(1.6);
        hourLater.iob.should.be.greaterThan(1.3);

        //hourLater.bolussnooze.should.be.lessThan(1.7);
        hourLater.iob.should.be.greaterThan(0);
        hourLater.activity.should.be.greaterThan(0.006);
        hourLater.activity.should.be.lessThan(0.015);

        var afterDIAInputs = inputs;
        afterDIAInputs.clock = new Date(now + (5 * 60 * 60 * 1000)).toISOString();
        var afterDIA = iob(afterDIAInputs)[0];
        afterDIA.iob.should.equal(0);
        //afterDIA.bolussnooze.should.equal(0);
    });

    it('should calculate IOB with Ultra-fast peak setting of 55', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 1,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 5,
                    insulinPeakTime: 55,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1,
                    curve: 'ultra-rapid'
                }
            };

        var rightAfterBolus = iob(inputs)[0];
        rightAfterBolus.iob.should.equal(1);
        //rightAfterBolus.bolussnooze.should.equal(1);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(0.75);
        //hourLater.bolussnooze.should.be.lessThan(0.75);
        hourLater.iob.should.be.greaterThan(0);
        hourLater.activity.should.be.greaterThan(0.0065);
        hourLater.activity.should.be.lessThan(0.008);

        var afterDIAInputs = inputs;
        afterDIAInputs.clock = new Date(now + (5 * 60 * 60 * 1000)).toISOString();
        var afterDIA = iob(afterDIAInputs)[0];

        afterDIA.iob.should.equal(0);
        //afterDIA.bolussnooze.should.equal(0);
    });

    it('should calculate IOB with Ultra-fast curve peak setting of 65', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 1,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 5,
                    insulinPeakTime: 65,
                    useCustomPeakTime: true,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1,
                    curve: 'ultra-rapid'
                }
            };

        var rightAfterBolus = iob(inputs)[0];
        rightAfterBolus.iob.should.equal(1);
        //rightAfterBolus.bolussnooze.should.equal(1);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(0.77);
        //hourLater.bolussnooze.should.be.lessThan(0.36);
        hourLater.iob.should.be.greaterThan(0.72);
        //hourLater.bolussnooze.should.be.greaterThan(0.354);

        hourLater.activity.should.be.greaterThan(0.0055);
        hourLater.activity.should.be.lessThan(0.007);

        var afterDIAInputs = inputs;
        afterDIAInputs.clock = new Date(now + (5 * 60 * 60 * 1000)).toISOString();
        var afterDIA = iob(afterDIAInputs)[0];

        afterDIA.iob.should.equal(0);
        //afterDIA.bolussnooze.should.equal(0);
    });

    it('should calculate IOB with Ultra-rapid curve peak setting of 75', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 1,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 5,
                    insulinPeakTime: 75,
                    useCustomPeakTime: true,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1,
                    curve: 'ultra-rapid'
                }
            };

        var rightAfterBolus = iob(inputs)[0];
        rightAfterBolus.iob.should.equal(1);
        //rightAfterBolus.bolussnooze.should.equal(1);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(0.81);
        //hourLater.bolussnooze.should.be.lessThan(0.5);
        hourLater.iob.should.be.greaterThan(0.76);
        //hourLater.bolussnooze.should.be.greaterThan(0.40);

        hourLater.iob.should.be.greaterThan(0);
        hourLater.activity.should.be.greaterThan(0.0047);
        hourLater.activity.should.be.lessThan(0.007);

        var afterDIAInputs = inputs;
        afterDIAInputs.clock = new Date(now + (5 * 60 * 60 * 1000)).toISOString();
        var afterDIA = iob(afterDIAInputs)[0];

        afterDIA.iob.should.equal(0);
        //afterDIA.bolussnooze.should.equal(0);
    });

    it('should calculate IOB with Ultra-rapid curve peak setting of 44 and DIA = 6', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 1,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 6,
                    insulinPeakTime: 44,
                    useCustomPeakTime: true,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1,
                    curve: 'ultra-rapid'
                }
            };

        var rightAfterBolus = iob(inputs)[0];
        rightAfterBolus.iob.should.equal(1);
        //rightAfterBolus.bolussnooze.should.equal(1);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(0.59);
        //hourLater.bolussnooze.should.be.lessThan(0.23);

        hourLater.iob.should.be.greaterThan(0.57);
        //hourLater.bolussnooze.should.be.greaterThan(0.21);

        hourLater.activity.should.be.greaterThan(0.007);
        hourLater.activity.should.be.lessThan(0.0085);

        var afterDIAInputs = inputs;
        afterDIAInputs.clock = new Date(now + (6 * 60 * 60 * 1000)).toISOString();
        var afterDIA = iob(afterDIAInputs)[0];

        afterDIA.iob.should.equal(0);
        //afterDIA.bolussnooze.should.equal(0);
    });

    it('should calculate IOB with Rapid-acting', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 1,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 5,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1,
                    curve: 'rapid-acting'
                }
            };

        var rightAfterBolus = iob(inputs)[0];
        rightAfterBolus.iob.should.equal(1);
        //rightAfterBolus.bolussnooze.should.equal(1);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(0.8);
        //hourLater.bolussnooze.should.be.lessThan(.8);
        hourLater.iob.should.be.greaterThan(0);

        var afterDIAInputs = inputs;
        afterDIAInputs.clock = new Date(now + (5 * 60 * 60 * 1000)).toISOString();
        var afterDIA = iob(afterDIAInputs)[0];

        afterDIA.iob.should.equal(0);
        //afterDIA.bolussnooze.should.equal(0);
    });

    it('should force minimum 5 hour DIA with Rapid-acting', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 1,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 5,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1,
                    curve: 'rapid-acting'
                }
            };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (4 * 60 * 60 * 1000)).toISOString();

        var hourLaterWith5 = iob(hourLaterInputs)[0];

        console.error(hourLaterWith5.iob);

        hourLaterInputs.profile.dia = 3;

        var hourLaterWith4 = iob(hourLaterInputs)[0];

        console.error(hourLaterWith4.iob);

        hourLaterWith4.iob.should.equal(hourLaterWith5.iob);
    });

    //it('should snooze fast if bolussnooze_dia_divisor is high', function() {

        //var now = Date.now(),
            //timestamp = new Date(now).toISOString(),
            //inputs = {
                //clock: timestamp,
                //history: [{
                    //_type: 'Bolus',
                    //amount: 1,
                    //timestamp: timestamp
                //}],
                //profile: {
                    //dia: 3,
                    //bolussnooze_dia_divisor: 10
                //}
            //};

        //var snoozeInputs = inputs;
        //snoozeInputs.clock = new Date(now + (20 * 60 * 1000)).toISOString();
        //var snooze = iob(snoozeInputs)[0];
        //snooze.bolussnooze.should.equal(0);
    //});

    it('should calculate IOB with Temp Basals', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobInputs = inputs;
        var iobNow = iob(iobInputs)[0];

        //console.log(iobNow);
        iobNow.iob.should.be.lessThan(1);
        iobNow.iob.should.be.greaterThan(0.5);
    });

    it('should calculate IOB with Temp Basals and a basal profile', function() {

        var startingPoint = moment('2016-06-13 01:00:00.000');
        var timestamp = startingPoint.format();
        var timestampEarly = startingPoint.subtract(30, 'minutes').format();

        var basalprofile = [{
                'i': 0,
                'start': '00:00:00',
                'rate': 2,
                'minutes': 0
            },
            {
                'i': 1,
                'start': '01:00:00',
                'rate': 1,
                'minutes': 60
            }
        ];

        var inputs = {
            clock: timestamp,
            history: [{
                _type: 'TempBasal',
                rate: 2,
                date: timestamp,
                timestamp: timestamp
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestamp,
                timestamp: timestamp,
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestampEarly,
                timestamp: timestampEarly,
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestampEarly,
                timestamp: timestampEarly
            }],
            profile: {
                dia: 3,
                //bolussnooze_dia_divisor: 2,
                basalprofile: basalprofile
            }
        };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = moment('2016-06-13 01:30:00.000');
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(0.5);
        hourLater.iob.should.be.greaterThan(0.4);
    });

    it('should calculate IOB with Temp Basals that overlap midnight and a basal profile', function() {

        var basalprofile = [{
                'i': 0,
                'start': '00:00:00',
                'rate': 2,
                'minutes': 0
            },
            {
                'i': 1,
                'start': '00:15:00',
                'rate': 1,
                'minutes': 15
            },
            {
                'i': 2,
                'start': '00:45:00',
                'rate': 0.5,
                'minutes': 45
            }
        ];

        var startingPoint = moment('2016-06-13 00:15:00.000');
        var timestamp = startingPoint.format();
        var timestampEarly = startingPoint.subtract(30, 'minutes').format(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp,
                    timestamp: timestamp
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp,
                    timestamp: timestamp
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestampEarly,
                    timestamp: timestampEarly
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestampEarly,
                    timestamp: timestampEarly
                }],
                profile: {
                    dia: 3,
                    current_basal: 0.1,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile
                }
            };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = moment('2016-06-13 00:45:00.000'); //new Date(now + (30 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];

        hourLater.iob.should.be.lessThan(0.8);
        hourLater.iob.should.be.greaterThan(0.7);
    });

    it('should calculate IOB with Temp Basals that overlap each other', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var startingPoint = moment('2016-06-13 00:30:00.000');
        var timestamp = startingPoint;
        var timestampEarly = startingPoint.clone().subtract(30, 'minutes');

        var inputs = {
            clock: timestamp,
            history: [{
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestampEarly.unix(),
                timestamp: timestampEarly.format()
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestampEarly.unix(),
                timestamp: timestampEarly.format()
            }],
            profile: {
                dia: 3,
                current_basal: 0.1,
                max_daily_basal: 1,
                //bolussnooze_dia_divisor: 2,
                basalprofile: basalprofile
            }
        };

        var hourLater = iob(inputs)[0];

        var timestampEarly2 = startingPoint.clone().subtract(29, 'minutes');
        var timestampEarly3 = startingPoint.clone().subtract(28, 'minutes');

        var inputs = {
            clock: timestamp,
            history: [{
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestampEarly.unix(),
                timestamp: timestampEarly.format()
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestampEarly.unix(),
                timestamp: timestampEarly.format()
            }],
            profile: {
                dia: 3,
                current_basal: 0.1,
                max_daily_basal: 1,
                //bolussnooze_dia_divisor: 2,
                basalprofile: basalprofile
            }
        };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = moment('2016-06-13 00:30:00.000');
        var hourLater = iob(hourLaterInputs)[0];

        var inputs = {
            clock: timestamp,
            history: [{
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestampEarly.unix(),
                timestamp: timestampEarly.format()
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestampEarly.unix(),
                timestamp: timestampEarly.format()
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestampEarly2.unix(),
                timestamp: timestampEarly2.format()
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestampEarly2.unix(),
                timestamp: timestampEarly2.format()
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestampEarly3.unix(),
                timestamp: timestampEarly3.format()
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestampEarly3.unix(),
                timestamp: timestampEarly3.format()
            }],
            profile: {
                dia: 3,
                current_basal: 0.1,
                max_daily_basal: 1,
                //bolussnooze_dia_divisor: 2,
                basalprofile: basalprofile
            }
        };

        var hourLaterWithOverlap = iob(inputs)[0];

        hourLater.iob.should.be.greaterThan(hourLaterWithOverlap.iob - 0.05);
        hourLater.iob.should.be.lessThan(hourLaterWithOverlap.iob + 0.05);
    });

    it('should calculate IOB with Temp Basals that overlap midnight and a basal profile, part deux', function() {

        var basalprofile = [{
                'i': 0,
                'start': '00:00:00',
                'rate': 2,
                'minutes': 0
            },
            {
                'i': 1,
                'start': '00:15:00',
                'rate': 0.1,
                'minutes': 15
            },
            {
                'i': 1,
                'start': '00:30:00',
                'rate': 2,
                'minutes': 30
            },
            {
                'i': 1,
                'start': '00:45:00',
                'rate': 0.1,
                'minutes': 45
            }
        ];

        var startingPoint = moment('2016-06-13 23:45:00.000');
        var timestamp = startingPoint.format();
        var timestampEarly = startingPoint.subtract(30, 'minutes').format(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 60,
                    date: timestamp,
                    timestamp: timestamp
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 3,
                    current_basal: 0.1,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile
                }
            };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = moment('2016-06-14 00:45:00.000');
        var hourLater = iob(hourLaterInputs)[0];

        hourLater.iob.should.be.lessThan(1);
        hourLater.iob.should.be.greaterThan(0.8);
    });

    it('should calculate IOB without counting time pump suspended at end of basal', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestamp15mAgo = new Date(now - (15 * 60 * 1000)).toISOString(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp45mAgo = new Date(now - (45 * 60 * 1000)).toISOString(),
            timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString(),
            timestamp75mAgo = new Date(now - (75 * 60 * 1000)).toISOString(),

            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 0,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobInputs = inputs;

        // Calculate IOB with inputs that will be the same as
        var iobNowWithoutSuspend = iob(iobInputs)[0];

        inputs = {
            clock: timestamp,
            history: [{
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestamp60mAgo,
                timestamp: timestamp60mAgo
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestamp60mAgo,
                timestamp: timestamp60mAgo
            }, {
                _type: 'PumpSuspend',
                date: timestamp45mAgo,
                timestamp: timestamp45mAgo
            }, {
                _type: 'PumpResume',
                date: timestamp30mAgo,
                timestamp: timestamp30mAgo
            }],
            profile: {
                dia: 3,
                current_basal: 1,
                suspend_zeros_iob: true,
                max_daily_basal: 1,
                //bolussnooze_dia_divisor: 2,
                'basalprofile': basalprofile
            }
        };

        iobInputs = inputs;

        var iobNowWithSuspend = iob(iobInputs)[0];

        iobNowWithSuspend.iob.should.equal(iobNowWithoutSuspend.iob);
    });

    it('should calculate IOB without counting time pump suspended in middle of basal', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestamp15mAgo = new Date(now - (15 * 60 * 1000)).toISOString(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp45mAgo = new Date(now - (45 * 60 * 1000)).toISOString(),
            timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString(),
            timestamp75mAgo = new Date(now - (75 * 60 * 1000)).toISOString(),

            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 0,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }],
                profile: {
                    dia: 5,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobInputs = inputs;

        var iobNowWithoutSuspend = iob(iobInputs)[0];

        inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 45,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp60mAgo,
                    timestamp: timestamp60mAgo
                }, {
                    _type: 'PumpSuspend',
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'PumpResume',
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }],
                profile: {
                    dia: 5,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        iobInputs = inputs;

        var iobNowWithSuspend = iob(iobInputs)[0];

        iobNowWithSuspend.iob.should.equal(iobNowWithoutSuspend.iob);
    });

    it('should calculate IOB without counting time pump suspended surrounding a basal', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestamp15mAgo = new Date(now - (15 * 60 * 1000)).toISOString(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp45mAgo = new Date(now - (45 * 60 * 1000)).toISOString(),
            timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString(),
            timestamp75mAgo = new Date(now - (75 * 60 * 1000)).toISOString(),
            timestamp90mAgo = new Date(now - (90 * 60 * 1000)).toISOString(),

            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 45,
                    date: timestamp75mAgo,
                    timestamp: timestamp75mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 0,
                    date: timestamp75mAgo,
                    timestamp: timestamp75mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp90mAgo,
                    timestamp: timestamp90mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp90mAgo,
                    timestamp: timestamp90mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobInputs = inputs;

        var iobNowWithoutSuspend = iob(iobInputs)[0];

        inputs = {
            clock: timestamp,
            history: [{
                _type: 'PumpResume',
                date: timestamp30mAgo,
                timestamp: timestamp30mAgo
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestamp45mAgo,
                timestamp: timestamp45mAgo
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestamp45mAgo,
                timestamp: timestamp45mAgo
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 15,
                date: timestamp60mAgo,
                timestamp: timestamp60mAgo
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestamp60mAgo,
                timestamp: timestamp60mAgo
            }, {
                _type: 'PumpSuspend',
                date: timestamp75mAgo,
                timestamp: timestamp75mAgo
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestamp90mAgo,
                timestamp: timestamp90mAgo
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestamp90mAgo,
                timestamp: timestamp90mAgo
            }],
            profile: {
                dia: 3,
                current_basal: 1,
                suspend_zeros_iob: true,
                max_daily_basal: 1,
                //bolussnooze_dia_divisor: 2,
                'basalprofile': basalprofile
            }
        };

        iobInputs = inputs;

        var iobNowWithSuspend = iob(iobInputs)[0];

        iobNowWithSuspend.iob.should.equal(iobNowWithoutSuspend.iob);
    });

    it('should calculate IOB without counting time pump suspended at beginning of basal', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestamp15mAgo = new Date(now - (15 * 60 * 1000)).toISOString(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp45mAgo = new Date(now - (45 * 60 * 1000)).toISOString(),
            timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString(),
            timestamp75mAgo = new Date(now - (75 * 60 * 1000)).toISOString(),

            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 0,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobInputs = inputs;

        var iobNowWithoutSuspend = iob(iobInputs)[0];

        inputs = {
            clock: timestamp,
            history: [{
                _type: 'PumpSuspend',
                date: timestamp45mAgo,
                timestamp: timestamp45mAgo
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestamp45mAgo,
                timestamp: timestamp45mAgo
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestamp45mAgo,
                timestamp: timestamp45mAgo
            }, {
                _type: 'PumpResume',
                date: timestamp30mAgo,
                timestamp: timestamp30mAgo
            }],
            profile: {
                dia: 3,
                current_basal: 1,
                suspend_zeros_iob: true,
                max_daily_basal: 1,
                'basalprofile': basalprofile
            }
        };

        var iobInputs = inputs;

        var iobNowWithSuspend = iob(iobInputs)[0];

        iobNowWithSuspend.iob.should.equal(iobNowWithoutSuspend.iob);
    });

    it('should calculate IOB without counting time pump suspended when pump suspend prior to history start', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestamp15mAgo = new Date(now - (15 * 60 * 1000)).toISOString(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp45mAgo = new Date(now - (45 * 60 * 1000)).toISOString(),
            timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString(),
            timestamp75mAgo = new Date(now - (75 * 60 * 1000)).toISOString(),
            timestamp480mAgo = new Date(now - (480 * 60 * 1000)).toISOString(),

            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 435,
                    date: timestamp480mAgo,
                    timestamp: timestamp480mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 0,
                    date: timestamp480mAgo,
                    timestamp: timestamp480mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobInputs = inputs;

        var iobNowWithoutSuspend = iob(iobInputs)[0];

        inputs = {
            clock: timestamp,
            history: [{
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: timestamp60mAgo,
                timestamp: timestamp60mAgo
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: timestamp60mAgo,
                timestamp: timestamp60mAgo
            }, {
                _type: 'PumpResume',
                date: timestamp45mAgo,
                timestamp: timestamp45mAgo
            }],
            profile: {
                dia: 3,
                current_basal: 1,
                suspend_zeros_iob: true,
                max_daily_basal: 1,
                //bolussnooze_dia_divisor: 2,
                'basalprofile': basalprofile
            }
        };

        iobInputs = inputs;

        var iobNowWithSuspend = iob(iobInputs)[0];

        iobNowWithSuspend.iob.should.equal(iobNowWithoutSuspend.iob);
    });

    it('should calculate IOB without counting time pump suspended when pump is currently suspended', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];
        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestamp15mAgo = new Date(now - (15 * 60 * 1000)).toISOString(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp45mAgo = new Date(now - (45 * 60 * 1000)).toISOString(),
            timestamp60mAgo = new Date(now - (60 * 60 * 1000)).toISOString(),
            timestamp75mAgo = new Date(now - (75 * 60 * 1000)).toISOString(),

            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 15,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobInputs = inputs;

        var iobNowWithoutSuspend = iob(iobInputs)[0];

            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp45mAgo,
                    timestamp: timestamp45mAgo
                }, {
                    _type: 'PumpSuspend',
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    suspend_zeros_iob: true,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var iobNowWithSuspend = iob(iobInputs)[0];

        iobNowWithSuspend.iob.should.equal(iobNowWithoutSuspend.iob);
    });

    it('should not report negative IOB with Temp Basals and a basal profile with drastic changes', function() {

        var basalprofile = [{
                'i': 0,
                'start': '00:00:00',
                'rate': 0.1,
                'minutes': 0
            },
            {
                'i': 1,
                'start': '00:30:00',
                'rate': 2,
                'minutes': 30
            }
        ];

        var startingPoint = new Date('2016-06-13 00:00:00.000');
        var startingPoint2 = new Date('2016-06-13 00:30:00.000');
        var endPoint = new Date('2016-06-13 01:00:00.000');

        var inputs = {
            clock: endPoint,
            history: [{
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: startingPoint,
                timestamp: startingPoint
            }, {
                _type: 'TempBasal',
                rate: 0.1,
                date: startingPoint,
                timestamp: startingPoint
            }, {
                _type: 'TempBasal',
                rate: 2,
                date: startingPoint2,
                timestamp: startingPoint2
            }, {
                _type: 'TempBasalDuration',
                'duration (min)': 30,
                date: startingPoint2,
                timestamp: startingPoint2
            }],
            profile: {
                dia: 3,
                current_basal: 2,
                max_daily_basal: 2,
                //bolussnooze_dia_divisor: 2,
                'basalprofile': basalprofile
            }
        };

        var hourLaterInputs = inputs;
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.equal(0);
    });

    it('should calculate IOB with Temp Basal events that overlap', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp30mAgo = new Date(now - (30 * 60 * 1000)).toISOString(),
            timestamp31mAgo = new Date(now - (31 * 60 * 1000)).toISOString(),
            inputs = {
                clock: timestamp30mAgo,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp31mAgo,
                    timestamp: timestamp31mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp31mAgo,
                    timestamp: timestamp31mAgo
                }, {
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp30mAgo,
                    timestamp: timestamp30mAgo
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    max_daily_basal: 1,
                    'basalprofile': basalprofile
                }
            };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];

        hourLater.iob.should.be.lessThan(1);
        hourLater.iob.should.be.greaterThan(0);
    });

    it('should calculate IOB with Temp Basals that are lower than base rate', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 2,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestampEarly = new Date(now - (30 * 60 * 1000)).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestampEarly,
                    timestamp: timestampEarly
                }, {
                    _type: 'TempBasal',
                    rate: 1,
                    date: timestampEarly,
                    timestamp: timestampEarly
                }, {
                    _type: 'TempBasal',
                    rate: 1,
                    date: timestamp,
                    timestamp: timestamp
                }, {
                    _type: 'TempBasalDuration',
                    'duration (min)': 30,
                    date: timestamp,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 3,
                    current_basal: 2,
                    max_daily_basal: 2,
                    //bolussnooze_dia_divisor: 2,
                    'basalprofile': basalprofile
                }
            };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];

        hourLater.iob.should.be.lessThan(0);
        hourLater.iob.should.be.greaterThan(-1);
    });

    it('should show 0 IOB with Temp Basals if duration is not found', function() {

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestampEarly = new Date(now - (60 * 60 * 1000)).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    debug: "should show 0 IOB with Temp Basals if duration is not found",
                    _type: 'TempBasal',
                    rate: 2,
                    date: timestamp,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2
                }
            };

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];

        hourLater.iob.should.equal(0);
    });

    it('should show 0 IOB with Temp Basals if basal is percentage based', function() {

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            timestampEarly = new Date(now - (60 * 60 * 1000)).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                        _type: 'TempBasal',
                        temp: 'percent',
                        rate: 2,
                        date: timestamp,
                        timestamp: timestamp
                    },
                    {
                        _type: 'TempBasalDuration',
                        'duration (min)': 30,
                        date: timestamp,
                        timestamp: timestamp
                    }
                ],
                profile: {
                    dia: 3,
                    current_basal: 1,
                    max_daily_basal: 1,
                    //bolussnooze_dia_divisor: 2
                }
            };


        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];

        hourLater.iob.should.equal(0);
    });

    it('should calculate IOB using a 4 hour duration', function() {

        var basalprofile = [{
            'i': 0,
            'start': '00:00:00',
            'rate': 1,
            'minutes': 0
        }];

        var now = Date.now(),
            timestamp = new Date(now).toISOString(),
            inputs = {
                clock: timestamp,
                history: [{
                    _type: 'Bolus',
                    amount: 1,
                    timestamp: timestamp
                }],
                profile: {
                    dia: 4,
                    //bolussnooze_dia_divisor: 2,
                    basalprofile: basalprofile,
                    current_basal: 1,
                    max_daily_basal: 1
                }

            };

        var rightAfterBolus = iob(inputs)[0];
        rightAfterBolus.iob.should.equal(1);
        //rightAfterBolus.bolussnooze.should.equal(1);

        var hourLaterInputs = inputs;
        hourLaterInputs.clock = new Date(now + (60 * 60 * 1000)).toISOString();
        var hourLater = iob(hourLaterInputs)[0];
        hourLater.iob.should.be.lessThan(1);
        //hourLater.bolussnooze.should.be.lessThan(.5);
        hourLater.iob.should.be.greaterThan(0);

        var after3hInputs = inputs;
        after3hInputs.clock = new Date(now + (3 * 60 * 60 * 1000)).toISOString();
        var after3h = iob(after3hInputs)[0];
        after3h.iob.should.be.greaterThan(0);

        var after4hInputs = inputs;
        after4hInputs.clock = new Date(now + (4 * 60 * 60 * 1000)).toISOString();
        var after4h = iob(after4hInputs)[0];
        after4h.iob.should.equal(0);
    });

});
