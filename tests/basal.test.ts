import * as basal from '../lib/profile/basal'
import { BasalSchedule } from '../lib/types/Profile';

describe('Basal', function ( ) {

    const basalprofile: BasalSchedule[] = [
        {'i': 0, 'start': '00:00:00', 'rate': 0, 'minutes': 0},
        {'i': 1, 'start': '00:15:00', 'rate': 2, 'minutes': 15 },
        {'i': 1, 'start': '00:45:00', 'rate': 0.5, 'minutes': 45 }
    ];

    it('should find the right max daily basal', function() {
        const inputs = {'basals': basalprofile};
        const maxBasal = basal.maxDailyBasal(inputs);
        expect(maxBasal).toStrictEqual(2)
    });


    it('should find the right basal for a given moment', function() {
        const startingPoint = new Date('2016-06-13 00:20:00.000');
        const startingPoint2 = new Date('2016-06-13 01:00:00.000');
        let b = basal.basalLookup(basalprofile, startingPoint);
        expect(b).toStrictEqual(2)
        b = basal.basalLookup(basalprofile, startingPoint2);
        expect(b).toStrictEqual(0.5)
    });
});
