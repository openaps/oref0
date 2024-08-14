import { sort } from 'effect/Array'
import * as ISFSensitivity from '../types/ISFSensitivity'
import type { ISFProfile } from '../types/Profile'

export function isfLookup(
    isf_profile: ISFProfile,
    timestamp: Date | undefined,
    lastResult: ISFSensitivity.ISFSensitivity | null
): [number, ISFSensitivity.ISFSensitivity | null] {
    const nowDate = timestamp || new Date()

    const nowMinutes = nowDate.getHours() * 60 + nowDate.getMinutes()

    if (lastResult && nowMinutes >= lastResult.offset && nowMinutes < (lastResult.endOffset || 0)) {
        return [lastResult.sensitivity, lastResult]
    }

    const isf_data = sort(ISFSensitivity.Order)(isf_profile.sensitivities)

    let isfSchedule = isf_data[isf_data.length - 1]

    if (isf_data[0].offset !== 0) {
        return [-1, lastResult]
    }

    let endMinutes = 1440

    for (let i = 0; i < isf_data.length - 1; i++) {
        const currentISF = isf_data[i]
        const nextISF = isf_data[i + 1]
        if (nowMinutes >= currentISF.offset && nowMinutes < nextISF.offset) {
            endMinutes = nextISF.offset
            isfSchedule = isf_data[i]
            break
        }
    }

    return [
        isfSchedule.sensitivity,
        {
            ...isfSchedule,
            endOffset: endMinutes,
        },
    ]
}

export default isfLookup
