import * as O from 'effect/Order'

export interface MealTreatment {
    timestamp: string
    carbs: number
    nsCarbs: number
    bwCarbs: number
    bolus: number
    journalCarbs: number
}

export const Order: O.Order<MealTreatment> = O.make<MealTreatment>((a, b) =>
    O.Date(new Date(a.timestamp), new Date(b.timestamp))
)
