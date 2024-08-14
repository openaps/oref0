import { Schema } from '@effect/schema'

const SimpleIOB = Schema.Struct({
    iob: Schema.Number,
    activity: Schema.Number,
    basaliob: Schema.Number,
    bolusiob: Schema.Number,
    netbasalinsulin: Schema.Number,
    bolusinsulin: Schema.Number,
    time: Schema.String,
})

const LastTemp = Schema.Struct({
    rate: Schema.Number,
    timestamp: Schema.String,
    started_at: Schema.String,
    date: Schema.Number,
    duration: Schema.Number,
})

export const IOB = Schema.Struct({
    ...SimpleIOB.fields,
    iobWithZeroTemp: SimpleIOB,
    lastBolusTime: Schema.optional(Schema.Int),
    lastTemp: Schema.optional(LastTemp),
})

export type IOB = typeof IOB.Type
