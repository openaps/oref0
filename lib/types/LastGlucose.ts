import { Schema } from '@effect/schema'

export const LastGlucose = Schema.Struct({
    delta: Schema.Number,
    glucose: Schema.Number,
    noise: Schema.Number,
    short_avgdelta: Schema.Number,
    long_avgdelta: Schema.Number,
    date: Schema.Number,
    last_cal: Schema.Number,
    device: Schema.optional(Schema.String),
})

export type LastGlucose = typeof LastGlucose.Type
