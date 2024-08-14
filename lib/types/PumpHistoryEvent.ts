import { Schema } from '@effect/schema'
import * as O from 'effect/Order'

export const TempType = Schema.Literal('absolute', 'percent')

export type TempType = typeof TempType.Type

export const PumpHistoryEvent = Schema.Struct({
    _type: Schema.NonEmptyString,
    timestamp: Schema.String,
    id: Schema.optional(Schema.String),
    amount: Schema.optional(Schema.Number),
    duration: Schema.optional(Schema.Number),
    'duration (min)': Schema.optional(Schema.Number),
    rate: Schema.optional(Schema.Number),
    temp: Schema.optional(TempType),
    carb_input: Schema.optional(Schema.Number),
    carb_ratio: Schema.optional(Schema.Number),
    note: Schema.optional(Schema.String),
    isSMB: Schema.optional(Schema.Boolean),
    isExternal: Schema.optional(Schema.Boolean),
    // found in lib/bolus.ts
    programmed: Schema.optional(Schema.Number),
    // found in lib/bolus.ts
    bg: Schema.optional(Schema.Number),

    // BolusWizard: https://github.com/nightscout/cgm-remote-monitor/issues/4685
    food_estimate: Schema.optional(Schema.Number),
    unabsorbed_insulin_total: Schema.optional(Schema.Number),
    correction_estimate: Schema.optional(Schema.Number),
    unabsorbed_insulin_count: Schema.optional(Schema.Number),
    bolus_estimate: Schema.optional(Schema.Number),
    bg_target_high: Schema.optional(Schema.Number),
    bg_target_low: Schema.optional(Schema.Number),
    sensitivity: Schema.optional(Schema.Number),
})

export type PumpHistoryEvent = typeof PumpHistoryEvent.Type

export const Order: O.Order<PumpHistoryEvent> = O.mapInput(O.Date, a => new Date(a.timestamp))
