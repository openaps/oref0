import { Schema } from '@effect/schema'
import * as A from 'effect/Array'
import * as Order from 'effect/Order'
import { tz } from '../date'
import * as date from '../date'
import * as basalprofile from '../profile/basal'
import { NightscoutTreatment } from '../types/NightscoutTreatment'
import { PumpHistoryEvent } from '../types/PumpHistoryEvent'
import { Input } from './Input'
import type { BasalTreatment, BolusTreatment, InsulinTreatment } from './InsulinTreatment'

interface Splitter {
    type: 'recurring'
    minutes: number
}

interface PumpSuspendResume {
    timestamp: string
    started_at: Date
    date: number
    duration: number
}

function splitTimespanWithOneSplitter(event: BasalTreatment, splitter: Splitter) {
    if (splitter.type !== 'recurring') {
        return [event]
    }

    const startMinutes = event.started_at.getHours() * 60 + event.started_at.getMinutes()
    const endMinutes = startMinutes + event.duration

    if (
        !(
            event.duration > 30 ||
            (startMinutes < splitter.minutes && endMinutes > splitter.minutes) ||
            (endMinutes > 1440 && splitter.minutes < endMinutes - 1440)
        )
    ) {
        return [event]
    }

    // 1440 = one day; no clean way to check if the event overlaps midnight
    // so checking if end of event in minutes is past midnight

    let event1Duration = 0

    if (event.duration > 30) {
        event1Duration = 30
    } else {
        let splitPoint = splitter.minutes
        if (endMinutes > 1440) {
            splitPoint = 1440
        }
        event1Duration = splitPoint - startMinutes
    }

    const event1EndDate = new Date(event.started_at)
    event1EndDate.setMinutes(event1EndDate.getMinutes() + event1Duration)

    const event1 = {
        ...event,
        duration: event1Duration,
    }
    const event2 = {
        ...event,
        duration: event.duration - event1Duration,
        timestamp: date.format(event1EndDate),
        started_at: event1EndDate,
        date: event1EndDate.getTime(),
    }

    return [event1, event2]
}

function splitTimespan(event: BasalTreatment, splitterMoments: Splitter[]) {
    let results = [event]

    let splitFound = true

    while (splitFound) {
        let resultArray: BasalTreatment[] = []
        splitFound = false

        for (let i = 0; i < results.length; i++) {
            const o = results[i]
            for (let j = 0; j < splitterMoments.length; j++) {
                const p = splitterMoments[j]
                const splitResult = splitTimespanWithOneSplitter(o, p)
                if (splitResult.length > 1) {
                    resultArray = resultArray.concat(splitResult)
                    splitFound = true
                    break
                }
            }

            if (!splitFound) {
                resultArray = resultArray.concat([o])
            }
        }

        results = resultArray
    }

    return results
}

// Split currentEvent around any conflicting suspends
// by removing the time period from the event that
// overlaps with any suspend.
function splitAroundSuspends(
    currentEvent: BasalTreatment,
    pumpSuspends: PumpSuspendResume[],
    firstResumeTime: string | undefined,
    suspendedPrior: boolean,
    lastSuspendTime: string | undefined,
    currentlySuspended: boolean
): BasalTreatment[] {
    const events = []

    // @todo: check why it can be undefined
    const firstResumeStarted = firstResumeTime ? new Date(firstResumeTime) : new Date(0)
    const firstResumeDate = firstResumeStarted.getTime()

    // @todo: check why it can be undefined
    const lastSuspendStarted = lastSuspendTime ? new Date(lastSuspendTime) : new Date()
    const lastSuspendDate = lastSuspendStarted.getTime()

    if (suspendedPrior && currentEvent.date < firstResumeDate) {
        if (currentEvent.date + currentEvent.duration * 60 * 1000 < firstResumeDate) {
            currentEvent.duration = 0
        } else {
            currentEvent.duration =
                (currentEvent.date + currentEvent.duration * 60 * 1000 - firstResumeDate) / 60 / 1000

            currentEvent.started_at = tz(firstResumeStarted)
            currentEvent.date = firstResumeDate
        }
    }

    if (currentlySuspended && currentEvent.date + currentEvent.duration * 60 * 1000 > lastSuspendDate) {
        if (currentEvent.date > lastSuspendDate) {
            currentEvent.duration = 0
        } else {
            currentEvent.duration = (firstResumeDate - currentEvent.date) / 60 / 1000
        }
    }

    events.push(currentEvent)

    if (currentEvent.duration === 0) {
        // bail out rather than wasting time going through the rest of the suspend events
        return events
    }

    for (let i = 0; i < pumpSuspends.length; i++) {
        const suspend = pumpSuspends[i]

        for (let j = 0; j < events.length; j++) {
            if (events[j].date <= suspend.date && events[j].date + events[j].duration * 60 * 1000 > suspend.date) {
                // event started before the suspend, but finished after the suspend started

                if (events[j].date + events[j].duration * 60 * 1000 > suspend.date + suspend.duration * 60 * 1000) {
                    const event2StartDate = new Date(suspend.started_at)
                    event2StartDate.setMinutes(event2StartDate.getMinutes() + suspend.duration)

                    events.push({
                        ...events[j],
                        timestamp: date.format(event2StartDate),
                        started_at: tz(event2StartDate),
                        date: suspend.date + suspend.duration * 60 * 1000,
                        duration:
                            (events[j].date +
                                events[j].duration * 60 * 1000 -
                                (suspend.date + suspend.duration * 60 * 1000)) /
                            60 /
                            1000,
                    })
                }

                events[j].duration = (suspend.date - events[j].date) / 60 / 1000
            } else if (suspend.date <= events[j].date && suspend.date + suspend.duration * 60 * 1000 > events[j].date) {
                // suspend started before the event, but finished after the event started

                events[j].duration =
                    (events[j].date + events[j].duration * 60 * 1000 - (suspend.date + suspend.duration * 60 * 1000)) /
                    60 /
                    1000

                const eventStartDate = new Date(suspend.started_at)
                eventStartDate.setMinutes(eventStartDate.getMinutes() + suspend.duration)

                events[j].timestamp = date.format(eventStartDate)
                events[j].started_at = tz(new Date(events[j].timestamp))
                events[j].date = suspend.date + suspend.duration * 60 * 1000
            }
        }
    }

    return events
}

export function generate(input: unknown, zeroTempDuration?: number) {
    const inputs = Schema.decodeUnknownSync(Input)(input)
    return findInsulin(inputs, zeroTempDuration)
}

export function findInsulin(inputs: Input, zeroTempDuration?: number): InsulinTreatment[] {
    const pumpHistory = [...inputs.history, ...(inputs.history24 || [])]
    const profile_data = inputs.profile
    const autosens_data = inputs.autosens
    let tempHistory: BasalTreatment[] = []
    const tempBoluses: BolusTreatment[] = []
    let pumpSuspends: PumpSuspendResume[] = []
    let pumpResumes: PumpSuspendResume[] = []
    let suspendedPrior = false
    let firstResumeTime: string | undefined
    let lastSuspendTime: string | undefined
    let currentlySuspended = false

    // @todo: check if clock can be undefined
    const now = tz(inputs.clock ? new Date(inputs.clock) : new Date())

    let lastRecordTime = now

    // Gather the times the pump was suspended and resumed
    for (let i = 0; i < pumpHistory.length; i++) {
        const current = pumpHistory[i]

        if (
            !Schema.is(PumpHistoryEvent)(current) ||
            (current._type !== 'PumpSuspend' && current._type !== 'PumpResume')
        ) {
            continue
        }

        const started_at = tz(new Date(current.timestamp))
        const temp = {
            timestamp: current.timestamp,
            started_at,
            date: started_at.getTime(),
            duration: 0,
        }

        if (current._type === 'PumpSuspend') {
            pumpSuspends.push(temp)
        } else if (current._type === 'PumpResume') {
            pumpResumes.push(temp)
        }
    }

    pumpSuspends = A.sort(pumpSuspends, Order.struct({ date: Order.number }))
    pumpResumes = A.sort(pumpResumes, Order.struct({ date: Order.number }))

    if (pumpResumes.length > 0) {
        firstResumeTime = pumpResumes[0].timestamp

        // Check to see if our first resume was prior to our first suspend
        // indicating suspend was prior to our first event.
        if (pumpSuspends.length === 0 || pumpResumes[0].date < pumpSuspends[0].date) {
            suspendedPrior = true
        }
    }

    let j = 0 // matching pumpResumes entry;

    let iSuspends = 0
    // Match the resumes with the suspends to get durations
    for (iSuspends = 0; iSuspends < pumpSuspends.length; iSuspends++) {
        for (; j < pumpResumes.length; j++) {
            if (pumpResumes[j].date > pumpSuspends[iSuspends].date) {
                break
            }
        }

        if (j >= pumpResumes.length && !currentlySuspended) {
            // even though it isn't the last suspend, we have reached
            // the final suspend. Set resume last so the
            // algorithm knows to suspend all the way
            // through the last record beginning at the last suspend
            // since we don't have a matching resume.
            currentlySuspended = true
            lastSuspendTime = pumpSuspends[iSuspends].timestamp

            break
        }

        pumpSuspends[iSuspends].duration = (pumpResumes[j].date - pumpSuspends[iSuspends].date) / 60 / 1000
    }

    // These checks indicate something isn't quite aligned.
    // Perhaps more resumes that suspends or vice versa...
    if (!suspendedPrior && !currentlySuspended && pumpResumes.length !== pumpSuspends.length) {
        console.error(`Mismatched number of resumes(${pumpResumes.length}) and suspends(${pumpSuspends.length})!`)
    } else if (suspendedPrior && !currentlySuspended && pumpResumes.length - 1 !== pumpSuspends.length) {
        console.error(
            `Mismatched number of resumes(${pumpResumes.length}) and suspends(${pumpSuspends.length}) assuming suspended prior to history block!`
        )
    } else if (!suspendedPrior && currentlySuspended && pumpResumes.length !== pumpSuspends.length - 1) {
        console.error(
            `Mismatched number of resumes(${pumpResumes.length}) and suspends(${pumpSuspends.length}) assuming suspended past end of history block!`
        )
    } else if (suspendedPrior && currentlySuspended && pumpResumes.length !== pumpSuspends.length) {
        console.error(
            `Mismatched number of resumes(${pumpResumes.length}) and suspends(${pumpSuspends.length}) assuming suspended prior to and past end of history block!`
        )
    }

    if (iSuspends < pumpSuspends.length - 1) {
        // truncate any extra suspends. if we had any extras
        // the error checks above would have issued a error log message
        pumpSuspends.splice(iSuspends + 1, pumpSuspends.length - iSuspends - 1)
    }

    // Pick relevant events for processing and clean the data

    for (let i = 0; i < pumpHistory.length; i++) {
        let current: NightscoutTreatment | PumpHistoryEvent = pumpHistory[i]
        if (Schema.is(NightscoutTreatment)(current) && current.bolus && current.bolus._type === 'Bolus') {
            current = current.bolus
        }

        const timestamp = Schema.is(NightscoutTreatment)(current) ? current.created_at : current.timestamp
        const currentRecordTime = tz(new Date(timestamp))
        //console.error(current);
        //console.error(currentRecordTime,lastRecordTime);
        // ignore duplicate or out-of-order records (due to 1h and 24h overlap, or timezone changes)
        if (currentRecordTime > lastRecordTime) {
            //console.error("",currentRecordTime," > ",lastRecordTime);
            //process.stderr.write(".");
            continue
        } else {
            lastRecordTime = currentRecordTime
        }
        if (Schema.is(PumpHistoryEvent)(current) && current._type === 'Bolus') {
            const started_at = tz(new Date(current.timestamp))
            if (started_at > now) {
                //console.error("Warning: ignoring",current.amount,"U bolus in the future at",temp.started_at);
                process.stderr.write(` ${current.amount}U @ ${started_at}`)
            } else {
                // @todo check for undefined insulin
                tempBoluses.push({
                    timestamp: current.timestamp,
                    started_at,
                    date: started_at.getTime(),
                    insulin: current.amount!,
                })
            }
        } else if (
            Schema.is(NightscoutTreatment)(current) &&
            (current.eventType === 'Meal Bolus' ||
                current.eventType === 'Correction Bolus' ||
                current.eventType === 'Snack Bolus' ||
                current.eventType === 'Bolus Wizard')
        ) {
            //imports treatments entered through Nightscout Care Portal
            //"Bolus Wizard" refers to the Nightscout Bolus Wizard, not the Medtronic Bolus Wizard
            const started_at = tz(new Date(current.created_at))
            // @todo check for undefined insulin
            tempBoluses.push({
                timestamp: current.created_at,
                started_at,
                date: started_at.getTime(),
                insulin: current.insulin!,
            })
        } else if (Schema.is(NightscoutTreatment)(current) && current.enteredBy === 'xdrip') {
            const started_at = tz(new Date(current.created_at))
            // @todo check for undefined insulin
            tempBoluses.push({
                timestamp: current.created_at,
                started_at,
                date: started_at.getTime(),
                insulin: current.insulin!,
            })
        } else if (Schema.is(NightscoutTreatment)(current) && current.enteredBy === 'HAPP_App' && current.insulin) {
            const started_at = tz(new Date(current.created_at))
            // @todo check for undefined insulin
            tempBoluses.push({
                timestamp: current.created_at,
                started_at,
                date: started_at.getTime(),
                insulin: current.insulin!,
            })
        } else if (
            Schema.is(NightscoutTreatment)(current) &&
            current.eventType === 'Temp Basal' &&
            (current.enteredBy === 'HAPP_App' || current.enteredBy === 'openaps://AndroidAPS')
        ) {
            const started_at = tz(new Date(current.created_at))
            // @todo check for undefined rate and duration
            tempHistory.push({
                timestamp: current.created_at,
                started_at,
                date: started_at.getTime(),
                rate: current.absolute!,
                duration: current.duration!,
            })
        } else if (Schema.is(NightscoutTreatment)(current) && current.eventType === 'Temp Basal') {
            const started_at = tz(new Date(current.created_at))
            let rate = current.rate
            // Loop reports the amount of insulin actually delivered while the temp basal was running
            // use that to calculate the effective temp basal rate
            if (typeof current.amount !== 'undefined') {
                // @todo: fix type for duration possibly undefined
                rate = (current.amount / current.duration!) * 60
            }
            // @todo check for undefined rate and duration
            tempHistory.push({
                timestamp: current.created_at,
                started_at,
                date: started_at.getTime(),
                rate: rate!,
                duration: current.duration!,
            })
        } else if (Schema.is(PumpHistoryEvent)(current) && current._type === 'TempBasal') {
            if (current.temp === 'percent') {
                continue
            }
            const rate = current.rate
            let duration
            const previous = i > 0 ? pumpHistory[i - 1] : undefined
            if (
                Schema.is(PumpHistoryEvent)(previous) &&
                previous.timestamp === timestamp &&
                previous._type === 'TempBasalDuration'
            ) {
                duration = previous['duration (min)']
            } else {
                for (let iter = 0; iter < pumpHistory.length; iter++) {
                    const item = pumpHistory[iter]
                    if (
                        Schema.is(PumpHistoryEvent)(item) &&
                        item.timestamp === timestamp &&
                        item._type === 'TempBasalDuration'
                    ) {
                        duration = item['duration (min)']
                        break
                    }
                }

                if (duration === undefined) {
                    console.error(
                        `No duration found for ${rate} U/hr basal ${timestamp}`,
                        pumpHistory[i - 1],
                        current,
                        pumpHistory[i + 1]
                    )
                }
            }

            const started_at = tz(new Date(current.timestamp))
            // @todo check for undefined rate and duration
            tempHistory.push({
                timestamp: current.timestamp,
                started_at,
                date: started_at.getTime(),
                rate: rate!,
                duration: duration!,
            })
        }

        // Add a temp basal cancel event to ignore future temps and reduce predBG oscillation
        // start the zero temp 1m in the future to avoid clock skew
        const started_atTemp = new Date(now.getTime() + 1 * 60 * 1000)
        tempHistory.push({
            timestamp: started_atTemp.toISOString(),
            started_at: started_atTemp,
            date: started_atTemp.getTime(),
            rate: 0,
            duration: zeroTempDuration || 0,
        })
    }

    // Check for overlapping events and adjust event lengths in case of overlap

    tempHistory = tempHistory.sort((a, b) => a.date - b.date)

    for (let i = 0; i < tempHistory.length - 1; i++) {
        const item = tempHistory[i]
        const next = tempHistory[i + 1]
        // @todo: check duration when undefined (or null)
        if (item.date + (item.duration || 0) * 60 * 1000 > next.date) {
            tempHistory[i].duration = (next.date - item.date) / 60 / 1000
            // Delete AndroidAPS "Cancel TBR records" in which duration is not populated
            if (next.duration === null || next.duration === undefined) {
                tempHistory.splice(i + 1, 1)
            }
        }
    }

    // Create an array of moments to slit the temps by
    // currently supports basal changes

    const splitterEvents = (profile_data.basalprofile || []).map(o => ({
        type: 'recurring' as const,
        minutes: o.minutes,
    }))

    // iterate through the events and split at basal break points if needed
    const splitHistoryByBasal = tempHistory.reduce(
        (b, o) => [...b, ...splitTimespan(o, splitterEvents)],
        [] as BasalTreatment[]
    )

    // @todo: not necessary: remove
    tempHistory = tempHistory.sort((a, b) => a.date - b.date)

    const suspend_zeros_iob = profile_data.suspend_zeros_iob || false
    let splitHistory = splitHistoryByBasal

    if (suspend_zeros_iob) {
        // iterate through the events and adjust their
        // times as required to account for pump suspends
        splitHistory = splitHistoryByBasal.reduce(
            (b, a) => [
                ...b,
                ...splitAroundSuspends(
                    a,
                    pumpSuspends,
                    firstResumeTime,
                    suspendedPrior,
                    lastSuspendTime,
                    currentlySuspended
                ),
            ],
            [] as BasalTreatment[]
        )

        // Any existing temp basals during times the pump was suspended are now deleted
        // Add 0 temp basals to negate the profile basal rates during times pump is suspended
        const zTempSuspendBasals = pumpSuspends.reduce(
            (b, a) => [...b, { ...a, rate: 0 }],
            [] as (PumpSuspendResume & { rate: number })[]
        )

        // Add temp suspend basal for maximum DIA (8) up to the resume time
        // if there is no matching suspend in the history before the first
        // resume
        const max_dia_ago = now.getTime() - 8 * 60 * 60 * 1000
        // @todo check why firstResumeStarted can be undefined
        const firstResumeStarted = firstResumeTime ? new Date(firstResumeTime) : new Date()
        const firstResumeDate = firstResumeStarted.getTime()

        // impact on IOB only matters if the resume occurred
        // after DIA hours before now.
        // otherwise, first resume date can be ignored. Whatever
        // insulin is present prior to resume will be aged
        // out due to DIA.
        if (suspendedPrior && max_dia_ago < firstResumeDate) {
            const suspendStart = new Date(max_dia_ago)
            const suspendStartDate = suspendStart.getTime()
            const started_at = tz(suspendStart)

            zTempSuspendBasals.push({
                rate: 0,
                duration: (firstResumeDate - max_dia_ago) / 60 / 1000,
                date: suspendStartDate,
                started_at,
                timestamp: suspendStart.toISOString(),
            })
        }

        if (currentlySuspended) {
            // @todo check why lastSuspendTime can be undefined
            const suspendStart = lastSuspendTime ? new Date(lastSuspendTime) : new Date()
            const suspendStartDate = suspendStart.getTime()
            const started_at = tz(suspendStart)

            // @todo check why lastSuspendTime can be undefined
            zTempSuspendBasals.push({
                rate: 0,
                duration: (now.getTime() - suspendStartDate) / 60 / 1000,
                date: suspendStartDate,
                started_at,
                timestamp: lastSuspendTime!,
            })
        }

        // Add the new 0 temp basals to the splitHistory.
        // We have to split the new zero temp basals by the profile
        // basals just like the other temp basals.
        splitHistory = zTempSuspendBasals.reduce((b, a) => [...b, ...splitTimespan(a, splitterEvents)], splitHistory)
    }

    splitHistory = splitHistory.sort((a, b) => a.date - b.date)

    // tempHistory = splitHistory;

    // iterate through the temp basals and create bolus events from temps that affect IOB

    for (let i = 0; i < splitHistory.length; i++) {
        const currentItem = splitHistory[i]

        if (currentItem.duration > 0) {
            let target_bg

            let currentRate = profile_data.current_basal
            if (profile_data.basalprofile && profile_data.basalprofile.length > 0) {
                const newCurrentRate = basalprofile.basalLookup(
                    profile_data.basalprofile,
                    new Date(currentItem.timestamp)
                )
                if (!newCurrentRate) {
                    // @todo: handle errors
                    throw new Error('Unable to find basal rate for iob time')
                }
                currentRate = newCurrentRate
            }

            if (typeof profile_data.min_bg !== 'undefined' && typeof profile_data.max_bg !== 'undefined') {
                target_bg = (profile_data.min_bg + profile_data.max_bg) / 2
            }
            //if (profile_data.temptargetSet && target_bg > 110) {
            //sensitivityRatio = 2/(2+(target_bg-100)/40);
            //currentRate = profile_data.current_basal * sensitivityRatio;
            //}
            let sensitivityRatio
            const profile = profile_data
            const normalTarget = 100 // evaluate high/low temptarget against 100, not scheduled basal (which might change)
            let halfBasalTarget = 160 // when temptarget is 160 mg/dL, run 50% basal (120 = 75%; 140 = 60%)
            if (profile.half_basal_exercise_target) {
                halfBasalTarget = profile.half_basal_exercise_target
            }
            if (profile.exercise_mode && profile.temptargetSet && target_bg && target_bg >= normalTarget + 5) {
                // w/ target 100, temp target 110 = .89, 120 = 0.8, 140 = 0.67, 160 = .57, and 200 = .44
                // e.g.: Sensitivity ratio set to 0.8 based on temp target of 120; Adjusting basal from 1.65 to 1.35; ISF from 58.9 to 73.6
                const c = halfBasalTarget - normalTarget
                sensitivityRatio = c / (c + target_bg - normalTarget)
            } else if (typeof autosens_data !== 'undefined') {
                sensitivityRatio = autosens_data.ratio
                //process.stderr.write("Autosens ratio: "+sensitivityRatio+"; ");
            }

            // @check why currentRate can be undefined
            currentRate = currentRate || 0
            if (sensitivityRatio) {
                currentRate = currentRate * sensitivityRatio
            }

            const netBasalRate = currentItem.rate - currentRate
            const tempBolusSize = netBasalRate < 0 ? -0.05 : 0.05
            const netBasalAmount = Math.round((netBasalRate * currentItem.duration * 10) / 6) / 100
            const tempBolusCount = Math.round(netBasalAmount / tempBolusSize)
            const tempBolusSpacing = currentItem.duration / tempBolusCount
            for (j = 0; j < tempBolusCount; j++) {
                const tempBolusDate = currentItem.date + j * tempBolusSpacing * 60 * 1000
                tempBoluses.push({
                    insulin: tempBolusSize,
                    date: tempBolusDate,
                    started_at: new Date(tempBolusDate),
                    timestamp: new Date(tempBolusDate).toISOString(),
                })
            }
        }
    }

    const all_data = [...tempBoluses, ...tempHistory]

    return all_data.sort((a, b) => a.date - b.date)
}

export default generate
