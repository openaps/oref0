import { Schema } from '@effect/schema'

export const GlucoseUnit = Schema.Literal('mg/dL', 'mmol/L').annotations({
    identifier: 'GlucoseUnit',
    title: 'Glucose Unit',
})

export type GlucoseUnit = typeof GlucoseUnit.Type
