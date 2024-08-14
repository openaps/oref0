import { Schema } from '@effect/schema'
import * as fs from 'fs'
import type { NightscoutTreatment } from './types/NightscoutTreatment'
import { PumpHistoryEvent } from './types/PumpHistoryEvent'

function withinMinutesFrom<A extends { timestamp: string }>(origin: A, tail: A[], minutes: number) {
    const ms = minutes * 1000 * 60
    const ts = Date.parse(origin.timestamp)
    return tail.slice().filter(elem => {
        const dt = Date.parse(elem.timestamp)
        return ts - dt <= ms
    })
}

function annotate<A extends NightscoutTreatment>(state: A, ...a: (string | number | undefined)[]): A {
    const notes = state.notes || ''
    return {
        ...state,
        notes: (notes.length > 0 ? '\n' : '') + a.join(' '),
    }
}

export function generate(treatments: unknown) {
    return reduce(Schema.decodeUnknownSync(Schema.Array(PumpHistoryEvent))(treatments))
}

export function reduce(treatments: ReadonlyArray<PumpHistoryEvent>) {
    const results: (NightscoutTreatment | PumpHistoryEvent)[] = []

    const previous: PumpHistoryEvent[] = []
    let state: NightscoutTreatment = {
        eventType: '<none>',
        created_at: new Date(0).toISOString(),
    }

    function bolus(ev: PumpHistoryEvent | null, remaining: PumpHistoryEvent[]) {
        if (ev && ev._type === 'BolusWizard') {
            state = {
                ...state,
                carbs: ev.carb_input,
                ratio: ev.carb_ratio,
                wizard: ev,
                timestamp: ev.timestamp,
                created_at: ev.timestamp,
                ...(ev.bg
                    ? {
                          bg: ev.bg,
                          glucose: ev.bg,
                          glucoseType: ev._type,
                      }
                    : undefined),
            }
            previous.push(ev)
        } else if (ev && ev._type === 'Bolus') {
            state = {
                ...state,
                duration: ev.duration,
                timestamp: ev.timestamp,
                created_at: ev.timestamp,
            }
            // if (state.square || state.bolus) { }
            // state.insulin = (state.insulin ? state.insulin : 0) + ev.amount;
            if (ev.duration && ev.duration > 0) {
                state = { ...state, square: ev }
            } else {
                if (state.bolus) {
                    state = {
                        ...state,
                        bolus: {
                            ...state.bolus,
                            amount: (state.bolus.amount || 0) + (ev.amount || 0),
                        },
                    }
                } else {
                    state = { ...state, bolus: ev }
                }
            }

            previous.push(ev)
        }

        if (remaining && remaining.length > 0) {
            if (state.bolus && state.wizard) {
                // skip to end
                return bolus(null, [])
            }
            // keep recursing
            return bolus(remaining[0], remaining.slice(1))
        } else {
            // console.error("state", state);
            // console.error("remaining", remaining);
            state = {
                ...state,
                eventType: '<none>',
                insulin: (state.insulin || 0) + (state.square?.amount || 0) + (state.bolus?.amount || 0),
            }
            const has_insulin = (state.insulin || 0) > 0
            const has_carbs = (state.carbs || 0) > 0
            if (state.square && state.bolus) {
                state = annotate(state, 'DualWave bolus for', state.square.duration, 'minutes')
            } else if (state.square && state.wizard) {
                state = annotate(state, 'Square wave bolus for', state.square.duration, 'minutes')
            } else if (state.square) {
                state = annotate(state, 'Solo Square wave bolus for', state.square.duration, 'minutes')
                state = annotate(state, 'No bolus wizard used.')
            } else if (state.bolus && state.wizard) {
                state = annotate(state, 'Normal bolus with wizard.')
            } else if (state.bolus) {
                state = annotate(state, 'Normal bolus (solo, no bolus wizard).')
            }

            if (has_insulin) {
                const iobFile = './monitor/iob.json'
                if (fs.existsSync(iobFile)) {
                    const iob = JSON.parse(fs.readFileSync(iobFile).toString())
                    if (iob && Array.isArray(iob) && iob.length) {
                        state = annotate(state, 'Calculated IOB:', iob[0].iob)
                    }
                }
            }

            if (state.bolus) {
                const amount = state.bolus.amount!
                const programmed = state.bolus.programmed !== undefined ? state.bolus.programmed : amount
                state = annotate(state, 'Programmed bolus', programmed)
                state = annotate(state, 'Delivered bolus', programmed)
                state = annotate(state, 'Percent delivered: ', `${((amount / programmed) * 100).toString()}%`)
            }
            if (state.square) {
                const square = state.square
                const amount = square.amount!
                const programmed = square.programmed !== undefined ? square.programmed : amount
                state = annotate(state, 'Programmed square', programmed)
                state = annotate(state, 'Delivered square', amount)
                state = annotate(state, 'Success: ', `${((amount / programmed) * 100).toString()}%`)
            }
            if (state.wizard) {
                const wizard = state.wizard
                state = { ...state, created_at: wizard.timestamp }
                state = annotate(state, 'Food estimate', wizard.food_estimate)
                state = annotate(state, 'Correction estimate', wizard.correction_estimate)
                state = annotate(state, 'Bolus estimate', wizard.bolus_estimate)
                state = annotate(state, 'Target low', wizard.bg_target_low)
                state = annotate(state, 'Target high', wizard.bg_target_high)
                const delta = wizard.sensitivity! * Number(state.insulin) * -1
                state = annotate(state, 'Hypothetical glucose delta', delta)
                if (state.bg && Number(state.bg) > 0) {
                    state = annotate(state, 'Glucose was:', state.bg)
                    // state.glucose = state.bg;
                    // TODO: annotate prediction
                }
            }
            if (has_carbs && has_insulin) {
                state = { ...state, eventType: 'Meal Bolus' }
            } else if (has_carbs && !has_insulin) {
                state = { ...state, eventType: 'Carb Correction' }
            } else if (!has_carbs && has_insulin) {
                state = { ...state, eventType: 'Correction Bolus' }
            } else {
                // else???
            }

            results.push(state)
            state = {
                eventType: '<none>',
                created_at: new Date(0).toISOString(),
            }
        }
    }

    function step(current: PumpHistoryEvent, index: number) {
        const inPrevious = previous.some(elem => elem.timestamp === current.timestamp && current._type === elem._type)
        if (inPrevious) {
            return
        }
        switch (current._type) {
            case 'Bolus':
            case 'BolusWizard':
                bolus(current, withinMinutesFrom(current, treatments.slice(index + 1), 2))
                break
            case 'JournalEntryMealMarker':
                results.push({
                    ...current,
                    carbs: current.carb_input,
                    eventType: 'Carb Correction',
                })
                break
            default:
                results.push({
                    ...current,
                })
                break
        }
    }
    treatments.forEach(step)
    return results
}

export default generate
