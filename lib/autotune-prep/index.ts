// Prep step before autotune.js can run; pulls in meal (carb) data and calls categorize.js

import { Schema } from '@effect/schema'
import { findMeals } from '../meal/history'
import { CarbEntry } from '../types/CarbEntry'
import * as GlucoseEntry from '../types/GlucoseEntry'
import { NightscoutTreatment } from '../types/NightscoutTreatment'
import { Profile } from '../types/Profile'
import { categorizeBGDatums as categorize } from './categorize'

const Input = Schema.Struct({
    history: Schema.Array(NightscoutTreatment),
    profile: Profile,
    pumpprofile: Profile,
    carbs: Schema.Array(CarbEntry),
    glucose: Schema.optionalWith(Schema.Array(GlucoseEntry.GlucoseEntry), { nullable: true }),
    categorize_uam_as_basal: Schema.optionalWith(Schema.Boolean, { default: () => false }),
    tune_insulin_curve: Schema.optionalWith(Schema.Boolean, { default: () => false }),
})

export function generate(input: unknown) {
    //console.error(inputs);
    const inputs = Schema.decodeUnknownSync(Input)(input)
    const treatments = findMeals(inputs)
    const profile = inputs.profile

    const opts = {
        treatments: treatments,
        profile: inputs.profile,
        pumpHistory: inputs.history,
        glucose: inputs.glucose || [],
        //, prepped_glucose: inputs.prepped_glucose
        basalprofile: inputs.profile.basalprofile,
        pumpbasalprofile: inputs.pumpprofile.basalprofile || false,
        categorize_uam_as_basal: inputs.categorize_uam_as_basal || false,
    }

    const diaDeviations = []
    const peakDeviations = []

    if (inputs.tune_insulin_curve) {
        if (profile.curve === 'bilinear') {
            console.error('--tune-insulin-curve is set but only valid for exponential curves')
        } else {
            let minDeviations = 1000000
            //let newDIA = 0
            const currentDIA = profile.dia

            const consoleError = console.error
            //console.error = function () {}

            const startDIA = currentDIA - 2
            const endDIA = currentDIA + 2
            for (let dia = startDIA; dia <= endDIA; ++dia) {
                let sqrtDeviations = 0
                let deviations = 0
                let deviationsSq = 0

                const curve_output = categorize({
                    ...opts,
                    profile: {
                        ...profile,
                        dia,
                    },
                })
                const basalGlucose = curve_output?.basalGlucoseData || []

                for (let hour = 0; hour < 24; ++hour) {
                    for (let i = 0; i < basalGlucose.length; ++i) {
                        const current = basalGlucose[i]
                        const BGTime = GlucoseEntry.getDate(current)

                        if (hour === BGTime.getHours()) {
                            //console.error(basalGlucose[i].deviation);
                            sqrtDeviations += Math.pow(Math.abs(basalGlucose[i].deviation), 0.5)
                            deviations += Math.abs(basalGlucose[i].deviation)
                            deviationsSq += Math.pow(basalGlucose[i].deviation, 2)
                        }
                    }
                }

                const meanDeviation = Math.round(Math.abs(deviations / basalGlucose.length) * 1000) / 1000
                const SMRDeviation = Math.round(Math.pow(sqrtDeviations / basalGlucose.length, 2) * 1000) / 1000
                const RMSDeviation = Math.round(Math.pow(deviationsSq / basalGlucose.length, 0.5) * 1000) / 1000
                consoleError(
                    'insulinEndTime',
                    dia,
                    'meanDeviation:',
                    meanDeviation,
                    'SMRDeviation:',
                    SMRDeviation,
                    'RMSDeviation:',
                    RMSDeviation,
                    '(mg/dL)'
                )
                diaDeviations.push({
                    dia: dia,
                    meanDeviation: meanDeviation,
                    SMRDeviation: SMRDeviation,
                    RMSDeviation: RMSDeviation,
                })

                deviations = Math.round(deviations * 1000) / 1000
                if (deviations < minDeviations) {
                    minDeviations = Math.round(deviations * 1000) / 1000
                    //newDIA = dia
                }
            }

            // consoleError('Optimum insulinEndTime', newDIA, 'mean deviation:', Math.round(minDeviations/basalGlucose.length*1000)/1000, '(mg/dL)');
            //consoleError(diaDeviations);

            minDeviations = 1000000

            //let newPeak = 0
            //consoleError(profile.useCustomPeakTime, profile.insulinPeakTime);
            let insulinPeakTime = profile.insulinPeakTime
            if (!profile.useCustomPeakTime === true && profile.curve === 'ultra-rapid') {
                insulinPeakTime = 55
            } else if (!profile.useCustomPeakTime === true) {
                insulinPeakTime = 75
            }

            const startPeak = insulinPeakTime - 10
            const endPeak = insulinPeakTime + 10
            for (let peak = startPeak; peak <= endPeak; peak = peak + 5) {
                let sqrtDeviations = 0
                let deviations = 0
                let deviationsSq = 0

                const curve_output = categorize({
                    ...opts,
                    profile: {
                        ...profile,
                        insulinPeakTime: peak,
                        useCustomPeakTime: true,
                    },
                })
                const basalGlucose = curve_output?.basalGlucoseData || []

                for (let hour = 0; hour < 24; ++hour) {
                    for (let i = 0; i < basalGlucose.length; ++i) {
                        const currentBasalGlucose = basalGlucose[i]
                        const BGTime = GlucoseEntry.getDate(currentBasalGlucose)

                        if (hour === BGTime.getHours()) {
                            //console.error(basalGlucose[i].deviation);
                            sqrtDeviations += Math.pow(Math.abs(currentBasalGlucose.deviation), 0.5)
                            deviations += Math.abs(currentBasalGlucose.deviation)
                            deviationsSq += Math.pow(currentBasalGlucose.deviation, 2)
                        }
                    }
                }
                console.error(deviationsSq)

                const meanDeviation = Math.round((deviations / basalGlucose.length) * 1000) / 1000
                const SMRDeviation = Math.round(Math.pow(sqrtDeviations / basalGlucose.length, 2) * 1000) / 1000
                const RMSDeviation = Math.round(Math.pow(deviationsSq / basalGlucose.length, 0.5) * 1000) / 1000
                consoleError(
                    'insulinPeakTime',
                    peak,
                    'meanDeviation:',
                    meanDeviation,
                    'SMRDeviation:',
                    SMRDeviation,
                    'RMSDeviation:',
                    RMSDeviation,
                    '(mg/dL)'
                )
                peakDeviations.push({
                    peak: peak,
                    meanDeviation: meanDeviation,
                    SMRDeviation: SMRDeviation,
                    RMSDeviation: RMSDeviation,
                })

                deviations = Math.round(deviations * 1000) / 1000
                if (deviations < minDeviations) {
                    minDeviations = Math.round(deviations * 1000) / 1000
                    //newPeak = peak
                }
            }

            //consoleError('Optimum insulinPeakTime', newPeak, 'mean deviation:', Math.round(minDeviations/basalGlucose.length*1000)/1000, '(mg/dL)');
            //consoleError(peakDeviations);

            console.error = consoleError
        }
    }

    return { ...categorize(opts), diaDeviations, peakDeviations }
}

export default generate
