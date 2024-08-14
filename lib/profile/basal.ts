import { sort } from 'effect/Array'
import * as BasalSchedule from '../types/BasalSchedule'
import type { Preferences } from '../types/Preferences'

/* Return basal rate(U / hr) at the provided timeOfDay */
export function basalLookup(schedules: readonly BasalSchedule.BasalSchedule[], now?: Date) {
    const nowDate = now || new Date()

    const basalprofile_data = sort(BasalSchedule.Order)(schedules)

    let basalRate = basalprofile_data[basalprofile_data.length - 1].rate
    // @todo: why can't be zero? I think a basal rate of 0 should be possibile
    if (basalRate === 0) {
        // TODO - shared node - move this print to shared object.
        throw new Error('ERROR: bad basal schedule')
    }
    const nowMinutes = nowDate.getHours() * 60 + nowDate.getMinutes()

    for (let i = 0; i < basalprofile_data.length - 1; i++) {
        if (nowMinutes >= basalprofile_data[i].minutes && nowMinutes < basalprofile_data[i + 1].minutes) {
            basalRate = basalprofile_data[i].rate
            break
        }
    }
    return Math.round(basalRate * 1000) / 1000
}

export function maxDailyBasal(inputs: Preferences): number {
    const max = inputs.basals.reduce((b, a) => (a.rate > b ? a.rate : b), 0)
    return (Number(max) * 1000) / 1000
}

/*Return maximum daily basal rate(U / hr) from profile.basals */

export function maxBasalLookup(inputs: Preferences): number | undefined {
    return inputs.settings.maxBasal
}

exports.maxDailyBasal = maxDailyBasal
exports.maxBasalLookup = maxBasalLookup
exports.basalLookup = basalLookup
