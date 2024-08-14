import { Schema } from '@effect/schema'

const BasalTreatment = Schema.Struct({
    timestamp: Schema.String,
    started_at: Schema.ValidDateFromSelf,
    date: Schema.Number,
    rate: Schema.Number,
    duration: Schema.Number,
})

export interface BasalTreatment {
    timestamp: string
    started_at: Date
    date: number
    rate: number
    duration: number
}

export interface BolusTreatment {
    timestamp: string
    started_at: Date
    date: number
    insulin: number
}

export type InsulinTreatment = BasalTreatment | BolusTreatment

export const isBasalTreatment = <A extends InsulinTreatment>(treatment: A): treatment is A & BasalTreatment =>
    Object.prototype.hasOwnProperty.call(treatment, 'rate')
export const isBolusTreatment = <A extends InsulinTreatment>(treatment: A): treatment is A & BolusTreatment =>
    Object.prototype.hasOwnProperty.call(treatment, 'insulin')
