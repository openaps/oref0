import { round_basal } from './round-basal'
import type { Profile } from './types/Profile'

interface RT {
    reason?: string
    duration?: number
    rate?: number
}

interface Temp {
    duration: number
    rate: number
}

function reason(rT: RT, msg: string) {
    rT.reason = (rT.reason ? `${rT.reason}. ` : '') + msg
    console.error(msg)
}

export function getMaxSafeBasal(profile: Profile) {
    const max_daily_safety_multiplier = profile.max_daily_safety_multiplier || 3
    const current_basal_safety_multiplier = profile.current_basal_safety_multiplier || 4

    return Math.min(
        profile.max_basal || 0,
        max_daily_safety_multiplier * (profile.max_daily_basal || 0),
        current_basal_safety_multiplier * (profile.current_basal || 0)
    )
}

export function setTempBasal(rateInput: number, duration: number, profile: Profile, rT: RT, currenttemp?: Temp) {
    //var maxSafeBasal = Math.min(profile.max_basal, 3 * profile.max_daily_basal, 4 * profile.current_basal);

    const maxSafeBasal = getMaxSafeBasal(profile)
    let rate = rateInput

    if (rate < 0) {
        rate = 0
    } else if (rate > maxSafeBasal) {
        rate = maxSafeBasal
    }

    const suggestedRate = round_basal(rate, profile)
    if (
        typeof currenttemp !== 'undefined' &&
        typeof currenttemp.duration !== 'undefined' &&
        typeof currenttemp.rate !== 'undefined' &&
        currenttemp.duration > duration - 10 &&
        currenttemp.duration <= 120 &&
        suggestedRate <= currenttemp.rate * 1.2 &&
        suggestedRate >= currenttemp.rate * 0.8 &&
        duration > 0
    ) {
        rT.reason += ` ${currenttemp.duration}m left and ${currenttemp.rate} ~ req ${
            suggestedRate
        }U/hr: no temp required`
        return rT
    }

    if (suggestedRate === profile.current_basal) {
        if (profile.skip_neutral_temps === true) {
            if (
                typeof currenttemp !== 'undefined' &&
                typeof currenttemp.duration !== 'undefined' &&
                currenttemp.duration > 0
            ) {
                reason(rT, 'Suggested rate is same as profile rate, a temp basal is active, canceling current temp')
                rT.duration = 0
                rT.rate = 0
                return rT
            } else {
                reason(rT, 'Suggested rate is same as profile rate, no temp basal is active, doing nothing')
                return rT
            }
        } else {
            reason(rT, `Setting neutral temp basal of ${profile.current_basal}U/hr`)
            rT.duration = duration
            rT.rate = suggestedRate
            return rT
        }
    } else {
        rT.duration = duration
        rT.rate = suggestedRate
        return rT
    }
}
