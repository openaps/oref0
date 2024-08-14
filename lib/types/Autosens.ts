import { Schema } from '@effect/schema'

export const Autosens = /*#__PURE__*/ Schema.Struct({
    timestamp: Schema.optional(Schema.String),
    ratio: Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)),
    newisf: Schema.optional(Schema.Number),
})

export type Autosens = typeof Autosens.Type
