import * as _ from '../lib/date'
import tz from 'moment-timezone'
import moment from 'moment'

describe('date', () => {
    const dates = [
        '2024-08-07T22:41:23.660Z',
        '2016-06-19T12:59:36-04:00',
        '2016-06-19T12:59:36-06:00',
        '2016-06-19T12:59:36+00:00',
        '2016-06-19T12:59:36+02:15',
    ]
    describe('tz', () => {
        it('should act like moment-timezone', () => {
            dates.forEach(dateString => {
                const a = new Date(tz(dateString))
                const b = _.tz(new Date(dateString))
                expect(b.toISOString()).toStrictEqual(a.toISOString())
                expect(b.getTimezoneOffset()).toStrictEqual(a.getTimezoneOffset())
            })
        })

        it('should act like moment-timezone from string', () => {
            dates.forEach(dateString => {
                const a = new Date(tz(dateString))
                const b = _.tz(dateString)
                expect(b.toISOString()).toStrictEqual(a.toISOString())
                expect(b.getTimezoneOffset()).toStrictEqual(a.getTimezoneOffset())
            })
        })
    })

    describe('format', () => {
        it('should act like moment.format()', () => {
            dates.forEach(dateString => {
                const a = moment(dateString).format()
                const b = _.format(new Date(dateString))
                expect(b).toStrictEqual(a)
            })
        })
    })
})
