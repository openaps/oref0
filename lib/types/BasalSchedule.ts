import { Schema } from '@effect/schema'
import * as O from 'effect/Order'
import * as ScheduleStart from './ScheduleStart'

export const BasalSchedule = Schema.Struct({
    i: Schema.optional(Schema.Int),
    start: Schema.optional(ScheduleStart.ScheduleStart),
    minutes: Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)),
    // @todo: why can't be zero? I think a basal rate of 0 should be possibile
    rate: Schema.Positive,
})

export type BasalSchedule = typeof BasalSchedule.Type

const OrderByI = O.mapInput<number | undefined, BasalSchedule>(
    (a, b) => (a === undefined || b === undefined ? 0 : O.number(a, b)),
    a => a.i
)

const OrderByStart = O.mapInput<string | undefined, BasalSchedule>(
    (a, b) => (a === undefined || b === undefined ? 0 : ScheduleStart.Order(a, b)),
    a => a.start
)

export const Order: O.Order<BasalSchedule> = O.combineAll([OrderByI, OrderByStart])
