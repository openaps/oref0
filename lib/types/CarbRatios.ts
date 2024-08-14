import { Schema } from '@effect/schema'
import { CarbRatioSchedule } from './CarbRatioSchedule'

export const CarbRatioUnit = Schema.Literal('grams', 'exchanges')
export type CarbRatioUnit = typeof CarbRatioUnit.Type

export const CarbRatios = Schema.Struct({
    units: CarbRatioUnit,
    schedule: Schema.Array(CarbRatioSchedule),
})

export type CarbRatios = typeof CarbRatios.Type
