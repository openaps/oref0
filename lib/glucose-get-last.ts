import { Schema } from '@effect/schema'
import { reduceWithGlucose, getDate, GlucoseEntry } from './types/GlucoseEntry'
import type { LastGlucose } from './types/LastGlucose'

function getDateFromEntry(entry: GlucoseEntry) {
    const date = getDate(entry)

    if (!date) {
        throw new TypeError('Unable to find a date in GlucoseEntry')
    }

    return date
}

export default function generate(input: unknown) {
    const glucoseData = Schema.decodeUnknownSync(Schema.Array(GlucoseEntry))(input)
    return getLastGlucose(glucoseData)
}

export const getLastGlucose = function (input: ReadonlyArray<GlucoseEntry>): LastGlucose {
    const data = reduceWithGlucose(input)

    const now = data[0]
    let now_date = getDateFromEntry(now).getTime()
    let change
    const last_deltas = []
    const short_deltas = []
    const long_deltas = []
    let last_cal = 0

    //console.error(now.glucose);
    for (let i = 1; i < data.length; i++) {
        // if we come across a cal record, don't process any older SGVs
        if (typeof data[i] !== 'undefined' && data[i].type === 'cal') {
            last_cal = i
            break
        }
        // only use data from the same device as the most recent BG data point
        if (typeof data[i] !== 'undefined' && data[i].glucose > 38 && data[i].device === now.device) {
            const then = data[i]
            const then_date = getDateFromEntry(then).getTime()
            let avgdelta = 0
            let minutesago
            if (typeof then_date !== 'undefined' && typeof now_date !== 'undefined') {
                minutesago = Math.round((now_date - then_date) / (1000 * 60))
                // multiply by 5 to get the same units as delta, i.e. mg/dL/5m
                change = now.glucose - then.glucose
                avgdelta = (change / minutesago) * 5
            } else {
                console.error('Error: date field not found: cannot calculate avgdelta')
                continue
            }
            //if (i < 5) {
            //console.error(then.glucose, minutesago, avgdelta);
            //}
            // use the average of all data points in the last 2.5m for all further "now" calculations
            if (-2 < minutesago && minutesago < 2.5) {
                now.glucose = (now.glucose + then.glucose) / 2
                now_date = (now_date + then_date) / 2
                //console.error(then.glucose, now.glucose);
                // short_deltas are calculated from everything ~5-15 minutes ago
            } else if (2.5 < minutesago && minutesago < 17.5) {
                //console.error(minutesago, avgdelta);
                short_deltas.push(avgdelta)
                // last_deltas are calculated from everything ~5 minutes ago
                if (2.5 < minutesago && minutesago < 7.5) {
                    last_deltas.push(avgdelta)
                }
                //console.error(then.glucose, minutesago, avgdelta, last_deltas, short_deltas);
                // long_deltas are calculated from everything ~20-40 minutes ago
            } else if (17.5 < minutesago && minutesago < 42.5) {
                long_deltas.push(avgdelta)
            }
        }
    }
    let last_delta = 0
    let short_avgdelta = 0
    let long_avgdelta = 0
    if (last_deltas.length > 0) {
        last_delta =
            last_deltas.reduce((a, b) => {
                return a + b
            }) / last_deltas.length
    }
    if (short_deltas.length > 0) {
        short_avgdelta =
            short_deltas.reduce((a, b) => {
                return a + b
            }) / short_deltas.length
    }
    if (long_deltas.length > 0) {
        long_avgdelta =
            long_deltas.reduce((a, b) => {
                return a + b
            }) / long_deltas.length
    }

    return {
        delta: Math.round(last_delta * 100) / 100,
        glucose: Math.round(now.glucose * 100) / 100,
        noise: Math.round(now.noise || 0),
        short_avgdelta: Math.round(short_avgdelta * 100) / 100,
        long_avgdelta: Math.round(long_avgdelta * 100) / 100,
        date: now_date,
        last_cal: last_cal,
        device: now.device,
    }
}
