import { Schema } from '@effect/schema'
import { Autosens } from '../types/Autosens'
import { NightscoutTreatment } from '../types/NightscoutTreatment'
import { Profile } from '../types/Profile'
import { PumpHistoryEvent } from '../types/PumpHistoryEvent'

export const Input = Schema.Struct({
    history: Schema.Array(Schema.Union(NightscoutTreatment, PumpHistoryEvent)),
    history24: Schema.optionalWith(Schema.Array(Schema.Union(NightscoutTreatment, PumpHistoryEvent)), {
        nullable: true,
    }),
    profile: Profile,
    autosens: Schema.optionalWith(Autosens, { nullable: true }),
    clock: Schema.optionalWith(Schema.String, { nullable: true }),
})

export type Input = typeof Input.Type
