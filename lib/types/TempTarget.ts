import { Schema } from '@effect/schema'
import * as O from 'effect/Order'

export const TempTarget = Schema.Struct({
    // @todo: should we just use strings?
    created_at: Schema.Union(Schema.DateFromSelf, Schema.String.pipe(Schema.nonEmptyString())),
    duration: Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)),
    targetTop: Schema.Int,
    targetBottom: Schema.Int,
}).annotations({
    title: 'TempTarget',
    description: 'Temp Target',
})

export type TempTarget = typeof TempTarget.Type

export const decode = Schema.decodeUnknownSync(TempTarget)

export const Order: O.Order<TempTarget> = O.mapInput(O.Date, a =>
    a.created_at instanceof Date ? a.created_at : new Date(a.created_at)
)
