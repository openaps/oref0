import { Schema } from '@effect/schema'
import { identity } from 'effect'
import * as O from 'effect/Order'

const pattern = '^([01][0-9]|2[0-3]):([0-5][0-9])(:([0-5][0-9]))?$'
export const ScheduleStart = Schema.String.pipe(Schema.pattern(new RegExp(pattern)))
    .pipe(
        Schema.transform(Schema.String, {
            decode: a => (a.split(':').length === 2 ? `${a}:00` : a),
            encode: identity,
        })
    )
    .annotations({
        description: 'Time in HH:MM:SS format',
    })

/**
 * Time in HH:MM
 */
export type ScheduleStart = typeof ScheduleStart.Type

export const Order: O.Order<ScheduleStart> = O.string
