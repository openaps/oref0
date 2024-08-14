import { Schema } from '@effect/schema'
import { tz } from '../date'
import { Input } from './Input'
import type { InsulinTreatment } from './InsulinTreatment'
import { isBasalTreatment, isBolusTreatment } from './InsulinTreatment'
import { findInsulin } from './history'
import { iobTotal as sum } from './total'

interface IOB {
    iob: number
    activity: number
    basaliob: number
    bolusiob: number
    netbasalinsulin: number
    bolusinsulin: number
    time: Date
}

interface IOBItem extends IOB {
    iobWithZeroTemp?: IOB
    lastBolusTime?: number
    lastTemp?: {
        date: number
        duration: number
    }
}

export const getIob = (inputs: Input, currentIOBOnly: boolean = false, inputTreatments?: InsulinTreatment[]) => {
    let treatmentsWithZeroTemp: InsulinTreatment[] = []
    let treatments = inputTreatments
    if (!treatments) {
        treatments = findInsulin(inputs)
        // calculate IOB based on continuous future zero temping as well
        treatmentsWithZeroTemp = findInsulin(inputs, 240)
    }

    //console.error(treatments.length, treatmentsWithZeroTemp.length);
    //console.error(treatments[treatments.length-1], treatmentsWithZeroTemp[treatmentsWithZeroTemp.length-1])

    const opts = {
        treatments: treatments,
        profile: inputs.profile,
        autosens: inputs.autosens,
    }
    const optsWithZeroTemp = {
        treatments: treatmentsWithZeroTemp,
        profile: inputs.profile,
    }

    if (!inputs.clock) {
        console.error('Clock is not defined')
        return []
    }

    const iobArray: IOBItem[] = []
    //console.error(inputs.clock);
    if (!/(Z|[+-][0-2][0-9]:?[034][05])+/.test(inputs.clock)) {
        console.error(`Warning: clock input ${inputs.clock} is unzoned; please pass clock-zoned.json instead`)
    }
    const clock = tz(new Date(inputs.clock))

    let lastBolusTime = new Date(0).getTime() //clock.getTime());
    let lastTemp = {
        date: new Date(0).getTime(), //clock.getTime());
        duration: 0,
    }

    //console.error(treatments[treatments.length-1]);
    treatments.forEach(treatment => {
        if (isBolusTreatment(treatment) && treatment.insulin > 0) {
            if (treatment.started_at.getTime() > lastBolusTime) {
                lastBolusTime = treatment.started_at.getTime()
            }
            //lastBolusTime = Math.max(lastBolusTime, treatment.started_at.getTime());
            //console.error(treatment.insulin,treatment.started_at,lastBolusTime);
        } else if (isBasalTreatment(treatment) && treatment.duration > 0) {
            if (treatment.date > lastTemp.date) {
                lastTemp = {
                    ...treatment,
                    duration: Math.round(treatment.duration * 100) / 100,
                }
            }

            //console.error(treatment.rate, treatment.duration, treatment.started_at,lastTemp.started_at)
        }
        //console.error(treatment.rate, treatment.duration, treatment.started_at,lastTemp.started_at)
        //if (treatment.insulin && treatment.started_at) { console.error(treatment.insulin,treatment.started_at,lastBolusTime); }
    })

    let iStop
    if (currentIOBOnly) {
        // for COB calculation, we only need the zeroth element of iobArray
        iStop = 1
    } else {
        // predict IOB out to 4h, regardless of DIA
        iStop = 4 * 60
    }
    for (let i = 0; i < iStop; i += 5) {
        const t = new Date(clock.getTime() + i * 60000)
        //console.error(t);
        const iob = sum(opts, t)
        const iobWithZeroTemp = sum(optsWithZeroTemp, t)

        if (!iob || !iobWithZeroTemp) {
            continue
        }
        //console.error(opts.treatments[opts.treatments.length-1], optsWithZeroTemp.treatments[optsWithZeroTemp.treatments.length-1])
        iobArray.push(iob)
        //console.error(iob.iob, iobWithZeroTemp.iob);
        //console.error(iobArray.length-1, iobArray[iobArray.length-1]);
        iobArray[iobArray.length - 1].iobWithZeroTemp = iobWithZeroTemp
    }

    //console.error(lastBolusTime);
    iobArray[0].lastBolusTime = lastBolusTime
    iobArray[0].lastTemp = lastTemp
    return iobArray
}

export default function generate(input: unknown) {
    const inputs = Schema.decodeUnknownSync(Input)(input, { errors: 'all' })
    return getIob(inputs)
}
