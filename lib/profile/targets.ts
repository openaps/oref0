import * as A from 'effect/Array'
import type { FinalResult } from '../bin/utils'
import { console_error } from '../bin/utils'
import { getTime } from '../medtronic-clock'
import type { Preferences } from '../types/Preferences'
import * as TempTarget from '../types/TempTarget'

interface BgTarget {
    offset: number
    low: number
    high: number
    temptargetSet?: boolean
}

export function bgTargetsLookup(final_result: FinalResult, inputs: Preferences) {
    return bound_target_range(lookup(final_result, inputs))
}

export function lookup(final_result: FinalResult, preferences: Preferences): BgTarget {
    const bgtargets_data = preferences.targets
    let temptargets_data = preferences.temptargets
    const now = new Date()

    //bgtargets_data.targets.sort(function (a, b) { return a.offset > b.offset });

    let bgTargets = bgtargets_data.targets[bgtargets_data.targets.length - 1]

    for (let i = 0; i < bgtargets_data.targets.length - 1; i++) {
        if (
            now.getTime() >= getTime(bgtargets_data.targets[i].offset) &&
            now.getTime() < getTime(bgtargets_data.targets[i + 1].offset)
        ) {
            bgTargets = bgtargets_data.targets[i]
            break
        }
    }

    const target_bg = preferences.target_bg || bgTargets.low

    let tempTargets: BgTarget = {
        ...bgTargets,
        low: target_bg,
        high: target_bg,
    }
    bgTargets = tempTargets

    if (temptargets_data.length === 0) {
        console_error(final_result, 'No temptargets found.')
        return bgTargets
    }

    // sort tempTargets by date so we can process most recent first
    temptargets_data = A.sort(temptargets_data, TempTarget.Order)

    for (let i = 0; i < temptargets_data.length; i++) {
        const start = new Date(temptargets_data[i].created_at)
        const expires = new Date(start.getTime() + temptargets_data[i].duration * 60 * 1000)
        if (now >= start && temptargets_data[i].duration === 0) {
            // cancel temp targets
            tempTargets = {
                ...bgTargets,
            }
            break
        } else if (!temptargets_data[i].targetBottom || !temptargets_data[i].targetTop) {
            console_error(
                final_result,
                `eventualBG target range invalid: ${temptargets_data[i].targetBottom}-${temptargets_data[i].targetTop}`
            )
            break
        } else if (now >= start && now < expires) {
            tempTargets = {
                ...tempTargets,
                high: temptargets_data[i].targetTop,
                low: temptargets_data[i].targetBottom,
                temptargetSet: true,
            }
            tempTargets.high = temptargets_data[i].targetTop
            tempTargets.low = temptargets_data[i].targetBottom
            tempTargets.temptargetSet = true
            break
        }
    }
    bgTargets = tempTargets

    return bgTargets
}

export function bound_target_range(target: BgTarget) {
    // if targets are < 20, assume for safety that they're intended to be mmol/L, and convert to mg/dL
    if (target.high < 20) {
        target.high = target.high * 18
    }
    if (target.low < 20) {
        target.low = target.low * 18
    }
    return {
        ...target,
        // hard-code lower bounds for min_bg and max_bg in case pump is set too low, or units are wrong
        // hard-code upper bound for min_bg in case pump is set too high
        max_bg: Math.min(200, Math.max(80, target.high)),
        min_bg: Math.min(200, Math.max(80, target.low)),
    }
}
