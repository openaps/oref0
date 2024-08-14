import type { NightscoutTreatment } from './types/NightscoutTreatment'
import type { PumpHistoryEvent } from './types/PumpHistoryEvent'

export function filter(treatments: ReadonlyArray<NightscoutTreatment | PumpHistoryEvent>) {
    const results: any[] = []

    let state: {
        eventType?: string
        invalid?: boolean
        duration?: string
        raw_duration?: PumpHistoryEvent
        raw_rate?: PumpHistoryEvent
        rate?: number | undefined
        timestamp?: string | undefined
        [k: string]: unknown
    } = {}
    function temp(ev: NightscoutTreatment | PumpHistoryEvent) {
        if ('duration (min)' in ev) {
            state.duration = ev['duration (min)']!.toString()
            state.raw_duration = ev
        }

        if ('rate' in ev && 'temp' in ev && ev.temp) {
            state[ev.temp] = ev.rate!.toString()
            state.rate = ev.rate
            state.raw_rate = ev
        }

        if ('timestamp' in state && ev.timestamp !== state.timestamp) {
            state.invalid = true
        } else {
            state.timestamp = ev.timestamp
        }

        if ('duration' in state && ('percent' in state || 'absolute' in state)) {
            state.eventType = 'Temp Basal'
            results.push(state)
            state = {}
        }
    }

    function step(current: any) {
        switch (current._type) {
            case 'TempBasalDuration':
            case 'TempBasal':
                temp(current)
                break
            default:
                results.push(current)
                break
        }
    }
    treatments.forEach(step)
    return results
}

export default filter
