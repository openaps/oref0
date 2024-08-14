import { Schema } from '@effect/schema'

export const TempBasal = Schema.Struct({
    duration: Schema.Int,
    temp: Schema.Literal('absolute', 'percent'),
    rate: Schema.Number,
})

export type TempBasal = typeof TempBasal.Type
