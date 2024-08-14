import { Schema } from '@effect/schema'
import * as O from 'effect/Order'

export const CarbEntry = Schema.Struct({
    carbs: Schema.optional(Schema.Number),
    created_at: Schema.optional(Schema.NonEmptyString),
})

export type CarbEntry = typeof CarbEntry.Type

export const Order: O.Order<CarbEntry> = (a, b) =>
    a.created_at && b.created_at ? O.Date(new Date(a.created_at), new Date(a.created_at)) : 0
