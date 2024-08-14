import { Schema } from '@effect/schema'
import * as O from 'effect/Order'
import * as ScheduleStart from './ScheduleStart'

export const CarbRatioSchedule = Schema.Struct({
    i: Schema.optional(Schema.Int),
    start: Schema.optional(ScheduleStart.ScheduleStart),
    offset: Schema.Number,
    ratio: Schema.Number,
})

export type CarbRatioSchedule = typeof CarbRatioSchedule.Type

const OrderByI = O.mapInput<number | undefined, CarbRatioSchedule>(
    (a, b) => (a === undefined || b === undefined ? 0 : O.number(a, b)),
    a => a.i
)

const OrderByStart = O.mapInput<string | undefined, CarbRatioSchedule>(
    (a, b) => (a === undefined || b === undefined ? 0 : ScheduleStart.Order(a, b)),
    a => a.start
)

export const Order: O.Order<CarbRatioSchedule> = O.combineAll([OrderByI, OrderByStart])
