import { Schema } from '@effect/schema'
import * as O from 'effect/Order'
import * as ScheduleStart from './ScheduleStart'

export const ISFSensitivity = Schema.Struct({
    offset: Schema.Number,
    endOffset: Schema.optional(Schema.Number),
    sensitivity: Schema.Number,
    i: Schema.optional(Schema.Number),
    start: Schema.optional(ScheduleStart.ScheduleStart),
    x: Schema.optional(Schema.Number),
})

export type ISFSensitivity = typeof ISFSensitivity.Type

const OrderByOffset: O.Order<ISFSensitivity> = O.struct({
    offset: O.number,
})

const OrderByI = O.mapInput<number | undefined, ISFSensitivity>(
    (a, b) => (a === undefined || b === undefined ? 0 : O.number(a, b)),
    a => a.i
)

const OrderByStart = O.mapInput<string | undefined, ISFSensitivity>(
    (a, b) => (a === undefined || b === undefined ? 0 : ScheduleStart.Order(a, b)),
    a => a.start
)

export const Order: O.Order<ISFSensitivity> = O.combineAll([OrderByOffset, OrderByI, OrderByStart])
