import * as A from 'effect/Array'
import { tz } from '../date'
import type { DetectCOBInput } from '../determine-basal/cob'
import { detectCarbAbsorption as detectCarbAbsorption } from '../determine-basal/cob'
import type { BasalSchedule } from '../types/BasalSchedule'
import type { GlucoseEntry } from '../types/GlucoseEntry'
import type { NightscoutTreatment } from '../types/NightscoutTreatment'
import type { Profile } from '../types/Profile'
import type { PumpHistoryEvent } from '../types/PumpHistoryEvent'
import * as MealTreatment from './MealTreatment'
import type { RecentCarbs } from './RecentCarbs'

export interface Options {
    treatments?: ReadonlyArray<MealTreatment.MealTreatment>
    pumphistory: ReadonlyArray<NightscoutTreatment | PumpHistoryEvent>
    profile: Profile
    basalprofile?: ReadonlyArray<BasalSchedule>
    glucose?: ReadonlyArray<GlucoseEntry>
    clock: string
}

export function totalRecentCarbs(opts: Options, time: Date): RecentCarbs {
    let treatments = opts.treatments
    const profile_data = opts.profile
    const glucose_data = opts.glucose
    let carbs = 0
    let nsCarbs = 0
    let bwCarbs = 0
    let journalCarbs = 0
    let bwFound = false
    const mealCarbTime = time.getTime()
    let lastCarbTime = 0

    if (!treatments) {
        return {
            carbs: Math.round(carbs * 1000) / 1000,
            nsCarbs: Math.round(nsCarbs * 1000) / 1000,
            bwCarbs: Math.round(bwCarbs * 1000) / 1000,
            journalCarbs: Math.round(journalCarbs * 1000) / 1000,
            mealCOB: 0,
            currentDeviation: 0,
            maxDeviation: 0,
            minDeviation: 0,
            slopeFromMaxDeviation: 0,
            slopeFromMinDeviation: 0,
            allDeviations: [],
            lastCarbTime: 0,
            bwFound: false,
        }
    }

    //console.error(glucose_data);
    const iob_inputs = {
        profile: profile_data,
        history: opts.pumphistory,
    }
    const COB_inputs: DetectCOBInput = {
        glucose_data: glucose_data || [],
        iob_inputs: iob_inputs,
        basalprofile: opts.basalprofile || [],
        mealTime: mealCarbTime,
    }
    let mealCOB = 0

    // this sorts the treatments collection in order.
    treatments = A.sort(treatments, MealTreatment.Order)

    let carbsToRemove = 0
    let nsCarbsToRemove = 0
    let bwCarbsToRemove = 0
    let journalCarbsToRemove = 0
    treatments.forEach(treatment => {
        const now = time.getTime()
        // consider carbs from up to 6 hours ago in calculating COB
        const carbWindow = now - 6 * 60 * 60 * 1000
        const treatmentDate = tz(new Date(treatment.timestamp))
        const treatmentTime = treatmentDate.getTime()
        if (treatmentTime > carbWindow && treatmentTime <= now) {
            if (treatment.carbs >= 1) {
                if (treatment.nsCarbs >= 1) {
                    nsCarbs += treatment.nsCarbs
                } else if (treatment.bwCarbs >= 1) {
                    bwCarbs += treatment.bwCarbs
                    bwFound = true
                } else if (treatment.journalCarbs >= 1) {
                    journalCarbs += treatment.journalCarbs
                } else {
                    console.error('Treatment carbs unclassified:', treatment)
                }
                //console.error(treatment.carbs, maxCarbs, treatmentDate);
                carbs += treatment.carbs
                COB_inputs.mealTime = treatmentTime
                lastCarbTime = Math.max(lastCarbTime, treatmentTime)
                const myCarbsAbsorbed = detectCarbAbsorption(COB_inputs).carbsAbsorbed //?????????????????????????????? here prfile was defined
                const myMealCOB = Math.max(0, carbs - myCarbsAbsorbed)
                if (typeof myMealCOB === 'number' && !isNaN(myMealCOB)) {
                    mealCOB = Math.max(mealCOB, myMealCOB)
                } else {
                    console.error(
                        'Bad myMealCOB:',
                        myMealCOB,
                        'mealCOB:',
                        mealCOB,
                        'carbs:',
                        carbs,
                        'myCarbsAbsorbed:',
                        myCarbsAbsorbed
                    )
                }
                if (myMealCOB < mealCOB) {
                    carbsToRemove += treatment.carbs
                    if (treatment.nsCarbs >= 1) {
                        nsCarbsToRemove += treatment.nsCarbs
                    } else if (treatment.bwCarbs >= 1) {
                        bwCarbsToRemove += treatment.bwCarbs
                    } else if (treatment.journalCarbs >= 1) {
                        journalCarbsToRemove += treatment.journalCarbs
                    }
                } else {
                    carbsToRemove = 0
                    nsCarbsToRemove = 0
                    bwCarbsToRemove = 0
                }
                //console.error(carbs, carbsToRemove);
                //console.error("COB:",mealCOB);
            }
        }
    })
    // only include carbs actually used in calculating COB
    carbs -= carbsToRemove
    nsCarbs -= nsCarbsToRemove
    bwCarbs -= bwCarbsToRemove
    journalCarbs -= journalCarbsToRemove

    // calculate the current deviation and steepest deviation downslope over the last hour
    COB_inputs.ciTime = time.getTime()
    // set mealTime to 6h ago for Deviation calculations
    COB_inputs.mealTime = time.getTime() - 6 * 60 * 60 * 1000
    const c = detectCarbAbsorption(COB_inputs)
    //console.error(c.currentDeviation, c.slopeFromMaxDeviation);

    // set a hard upper limit on COB to mitigate impact of erroneous or malicious carb entry
    if (profile_data.maxCOB !== undefined) {
        mealCOB = Math.min(profile_data.maxCOB, mealCOB)
    } else {
        console.error('Bad profile.maxCOB:', profile_data.maxCOB)
    }

    // if currentDeviation is null or maxDeviation is 0, set mealCOB to 0 for zombie-carb safety
    if (typeof c.currentDeviation === 'undefined' || c.currentDeviation === null) {
        console.error('')
        console.error('Warning: setting mealCOB to 0 because currentDeviation is null/undefined')
        mealCOB = 0
    }
    if (typeof c.maxDeviation === 'undefined' || c.maxDeviation === null) {
        console.error('')
        console.error('Warning: setting mealCOB to 0 because maxDeviation is 0 or undefined')
        mealCOB = 0
    }

    return {
        carbs: Math.round(carbs * 1000) / 1000,
        nsCarbs: Math.round(nsCarbs * 1000) / 1000,
        bwCarbs: Math.round(bwCarbs * 1000) / 1000,
        journalCarbs: Math.round(journalCarbs * 1000) / 1000,
        mealCOB: Math.round(mealCOB),
        currentDeviation: Math.round(c.currentDeviation * 100) / 100,
        maxDeviation: Math.round(c.maxDeviation * 100) / 100,
        minDeviation: Math.round(c.minDeviation * 100) / 100,
        slopeFromMaxDeviation: Math.round(c.slopeFromMaxDeviation * 1000) / 1000,
        slopeFromMinDeviation: Math.round(c.slopeFromMinDeviation * 1000) / 1000,
        allDeviations: c.allDeviations,
        lastCarbTime: lastCarbTime,
        bwFound: bwFound,
    }
}

export default totalRecentCarbs
