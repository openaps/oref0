import { Schema } from '@effect/schema'
import type { Autosens } from '../types/Autosens'
import { InsulineCurve } from '../types/InsulineCurve'
import type { Profile } from '../types/Profile'
import type { InsulinTreatment } from './InsulinTreatment'
import { isBolusTreatment } from './InsulinTreatment'
import { calculate } from './calculate'

interface Options {
    treatments: InsulinTreatment[]
    profile: Profile
    autosens?: Autosens | undefined
}

export function iobTotal(opts: Options, time: Date) {
    const now = time.getTime()
    const treatments = opts.treatments
    const profile_data = opts.profile
    let dia = profile_data.dia || 3
    let peak = 0
    let iob = 0
    let basaliob = 0
    let bolusiob = 0
    let netbasalinsulin = 0
    let bolusinsulin = 0
    //var bolussnooze = 0;
    let activity = 0
    if (!treatments) {
        return null
    }
    //if (typeof time === 'undefined') {
    //var time = new Date();
    //}

    // force minimum DIA of 3h
    if (dia < 3) {
        //console.error("Warning; adjusting DIA from",dia,"to minimum of 3 hours");
        dia = 3
    }

    const curveDefaults: {
        [k in InsulineCurve]: {
            requireLongDia: boolean
            peak: number
            tdMin?: number
        }
    } = {
        bilinear: {
            requireLongDia: false,
            peak: 75, // not really used, but prevents having to check later
        },
        'rapid-acting': {
            requireLongDia: true,
            peak: 75,
            tdMin: 300,
        },
        'ultra-rapid': {
            requireLongDia: true,
            peak: 55,
            tdMin: 300,
        },
    }

    let curve = profile_data.curve || 'bilinear'

    // @todo: remove when decoding
    if (!Schema.is(InsulineCurve)(curve)) {
        console.error(
            `Unsupported curve function: "${curve}". Supported curves: "bilinear", "rapid-acting" (Novolog, Novorapid, Humalog, Apidra) and "ultra-rapid" (Fiasp). Defaulting to "rapid-acting".`
        )
        curve = 'rapid-acting' as InsulineCurve
    }

    const defaults = curveDefaults[curve]

    // Force minimum of 5 hour DIA when default requires a Long DIA.
    if (defaults.requireLongDia && dia < 5) {
        //console.error('Pump DIA must be set to 5 hours or more with the new curves, please adjust your pump. Defaulting to 5 hour DIA.');
        dia = 5
    }

    peak = defaults.peak

    treatments.forEach(treatment => {
        if (treatment.date <= now) {
            const dia_ago = now - dia * 60 * 60 * 1000
            if (treatment.date > dia_ago) {
                // tIOB = total IOB
                const tIOB = calculate(treatment, time, curve, dia, peak, profile_data)

                if (tIOB && tIOB.iobContrib) {
                    iob += tIOB.iobContrib
                }
                if (tIOB && tIOB.activityContrib) {
                    activity += tIOB.activityContrib
                }
                // basals look like either of these:
                // {"insulin":-0.05,"date":1507265512363.6365,"created_at":"2017-10-06T04:51:52.363Z"}
                // {"insulin":0.05,"date":1507266530000,"created_at":"2017-10-06T05:08:50.000Z"}
                // boluses look like:
                // {"timestamp":"2017-10-05T22:06:31-07:00","started_at":"2017-10-06T05:06:31.000Z","date":1507266391000,"insulin":0.5}
                if (isBolusTreatment(treatment) && treatment.insulin && tIOB && tIOB.iobContrib) {
                    if (treatment.insulin < 0.1) {
                        basaliob += tIOB.iobContrib
                        netbasalinsulin += treatment.insulin
                    } else {
                        bolusiob += tIOB.iobContrib
                        bolusinsulin += treatment.insulin
                    }
                }
                //console.error(JSON.stringify(treatment));
            }
        } // else { console.error("ignoring future treatment:",treatment); }
    })

    return {
        iob: Math.round(iob * 1000) / 1000,
        activity: Math.round(activity * 10000) / 10000,
        basaliob: Math.round(basaliob * 1000) / 1000,
        bolusiob: Math.round(bolusiob * 1000) / 1000,
        netbasalinsulin: Math.round(netbasalinsulin * 1000) / 1000,
        bolusinsulin: Math.round(bolusinsulin * 1000) / 1000,
        time: time,
    }
}

export default iobTotal
