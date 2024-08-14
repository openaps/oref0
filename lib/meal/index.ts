import { Schema } from '@effect/schema'
import { tz } from '../date'
import { BasalSchedule } from '../types/BasalSchedule'
import { CarbEntry } from '../types/CarbEntry'
import { GlucoseEntry } from '../types/GlucoseEntry'
import { NightscoutTreatment } from '../types/NightscoutTreatment'
import { Profile } from '../types/Profile'
import { PumpHistoryEvent } from '../types/PumpHistoryEvent'
import { findMeals } from './history'
import { totalRecentCarbs as sum } from './total'

const Input = Schema.Struct({
    history: Schema.Array(Schema.Union(NightscoutTreatment, PumpHistoryEvent)),
    carbs: Schema.Array(CarbEntry),
    profile: Profile,
    basalprofile: Schema.optionalWith(Schema.Array(BasalSchedule), { nullable: true }),
    glucose: Schema.optionalWith(Schema.Array(GlucoseEntry), { nullable: true }),
    clock: Schema.String,
})

export function generate(input: unknown) {
    const inputs = Schema.decodeUnknownSync(Input)(input)
    const treatments = findMeals(inputs)

    const opts = {
        treatments: treatments,
        profile: inputs.profile,
        pumphistory: inputs.history,
        basalprofile: inputs.basalprofile || [],
        glucose: inputs.glucose || [],
        clock: inputs.clock,
    }

    const clock = tz(new Date(inputs.clock))

    return /* meal_data */ sum(opts, clock)
}

export default generate
