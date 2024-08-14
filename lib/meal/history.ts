//import { PumpEntry, PumpEntryBolusWizard } from "../types/PumpEntry.ts.bak";

import { Schema } from '@effect/schema'
import { dedupeWith, sort } from 'effect/Array'
import { struct, strict } from 'effect/Equivalence'
import type { CarbEntry } from '../types/CarbEntry'
import { NightscoutTreatment } from '../types/NightscoutTreatment'
import { PumpHistoryEvent } from '../types/PumpHistoryEvent'
import type { MealTreatment } from './MealTreatment'
import { Order } from './MealTreatment'

export interface Input {
    history: ReadonlyArray<PumpHistoryEvent | NightscoutTreatment>
    carbs: ReadonlyArray<CarbEntry>
}

interface TempMealTreatment extends MealTreatment {
    hasBolus: boolean
    hasCarbs: boolean
}

const createMeal = (timestamp: string, partial: Partial<MealTreatment>): TempMealTreatment => ({
    timestamp,
    carbs: partial.carbs || 0,
    nsCarbs: partial.nsCarbs || 0,
    bwCarbs: partial.bwCarbs || 0,
    bolus: partial.bolus || 0,
    journalCarbs: partial.journalCarbs || 0,
    hasBolus: partial.bolus !== undefined,
    hasCarbs: partial.carbs !== undefined,
})

export function findMeals(inputs: Input): MealTreatment[] {
    const pumpHistory = inputs.history
    const carbHistory = inputs.carbs
    const mealInputs: TempMealTreatment[] = []
    const bolusWizardInputs: PumpHistoryEvent[] = []

    const timestampEq = (a: string, b: string) => Math.abs(new Date(a).getTime() - new Date(b).getTime()) < 2000

    for (let i = 0; i < carbHistory.length; i++) {
        const current = carbHistory[i]
        if (current.carbs && current.created_at) {
            mealInputs.push(
                createMeal(current.created_at, {
                    carbs: current.carbs,
                    nsCarbs: current.carbs,
                })
            )
        }
    }

    for (let i = 0; i < pumpHistory.length; i++) {
        const current = pumpHistory[i]
        if (Schema.is(PumpHistoryEvent)(current) && current._type === 'Bolus' && current.timestamp && current.amount) {
            //console.log(pumpHistory[i]);
            mealInputs.push(createMeal(current.timestamp, { bolus: current.amount }))
        } else if (Schema.is(PumpHistoryEvent)(current) && current._type === 'BolusWizard' && current.timestamp) {
            // Delay process the BolusWizard entries to make sure we've seen all possible that correspond to the bolus wizard.
            // More specifically, we need to make sure we process the corresponding bolus entry first.
            bolusWizardInputs.push(current)
        } else if (
            Schema.is(NightscoutTreatment)(current) &&
            (current.eventType === 'Meal Bolus' ||
                current.eventType === 'Correction Bolus' ||
                current.eventType === 'Snack Bolus' ||
                current.eventType === 'Bolus Wizard' ||
                current.eventType === 'Carb Correction') &&
            current.carbs !== undefined
        ) {
            //imports carbs entered through Nightscout Care Portal
            //"Bolus Wizard" refers to the Nightscout Bolus Wizard, not the Medtronic Bolus Wizard

            // don't enter the treatment if there's another treatment with the same exact timestamp
            // to prevent duped carb entries from multiple sources
            mealInputs.push(
                createMeal(current.created_at, {
                    carbs: current.carbs,
                    nsCarbs: current.carbs,
                })
            )
        } else if (Schema.is(NightscoutTreatment)(current) && current.enteredBy === 'xdrip') {
            mealInputs.push(
                createMeal(current.created_at, {
                    carbs: current.carbs || 0,
                    nsCarbs: current.carbs || 0,
                    bolus: current.insulin || 0,
                })
            )
        } else if (Schema.is(NightscoutTreatment)(current) && current.carbs && current.carbs > 0) {
            mealInputs.push(
                createMeal(current.created_at, {
                    carbs: current.carbs || 0,
                    nsCarbs: current.carbs || 0,
                    bolus: current.insulin || 0,
                })
            )
        } else if (
            Schema.is(PumpHistoryEvent)(current) &&
            current._type === 'JournalEntryMealMarker' &&
            current.carb_input &&
            current.carb_input > 0
        ) {
            mealInputs.push(
                createMeal(current.timestamp, {
                    carbs: current.carb_input,
                    journalCarbs: current.carb_input,
                })
            )
        }
    }

    for (let i = 0; i < bolusWizardInputs.length; i++) {
        const current = bolusWizardInputs[i]
        //console.log(bolusWizardInputs[i]);
        const temp = createMeal(current.timestamp, {
            carbs: current.carb_input || 0,
            bwCarbs: current.carb_input || 0,
        })

        // don't enter the treatment if there's another treatment with the same exact timestamp
        // to prevent duped carb entries from multiple sources
        if (mealInputs.some(a => timestampEq(a.timestamp, current.timestamp) && a.hasCarbs)) {
            continue
        }

        if (!mealInputs.some(a => timestampEq(a.timestamp, current.timestamp) && a.hasBolus)) {
            console.error(
                'Skipping bolus wizard entry',
                i,
                'in the pump history with',
                current.carb_input,
                'g carbs and no insulin.'
            )
            continue
        }

        mealInputs.push(temp)
    }

    const eq = struct({
        timestamp: timestampEq,
        carbs: strict(),
        bolus: strict(),
    })
    return sort(dedupeWith<MealTreatment>(mealInputs, eq), Order)
}

export default findMeals
