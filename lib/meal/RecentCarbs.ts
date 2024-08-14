import { Schema } from '@effect/schema'

export const RecentCarbs = Schema.Struct({
    carbs: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    nsCarbs: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    bwCarbs: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    journalCarbs: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    mealCOB: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    currentDeviation: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    maxDeviation: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    minDeviation: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    slopeFromMaxDeviation: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    slopeFromMinDeviation: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    allDeviations: Schema.optionalWith(Schema.Array(Schema.Number), { default: () => [] }),
    lastCarbTime: Schema.optionalWith(Schema.Number, { default: () => 0 }),
    bwFound: Schema.optionalWith(Schema.Boolean, { default: () => false }),
})

export type RecentCarbs = typeof RecentCarbs.Type
