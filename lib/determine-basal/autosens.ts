import { Schema } from '@effect/schema'
import * as A from 'effect/Array'
import { tz } from '../date'
import { getIob } from '../iob'
import { findInsulin } from '../iob/history'
import * as MealTreatment from '../meal/MealTreatment'
import { findMeals } from '../meal/history'
import { percentile } from '../percentile'
import { basalLookup } from '../profile/basal'
import { isfLookup } from '../profile/isf'
import { BasalSchedule } from '../types/BasalSchedule'
import { CarbEntry } from '../types/CarbEntry'
import { GlucoseEntry, reduceWithGlucoseAndDate } from '../types/GlucoseEntry'
import type { ISFSensitivity } from '../types/ISFSensitivity'
import * as TempTarget from '../types/TempTarget'

const Inputs = Schema.Struct({
    glucose_data: Schema.Array(GlucoseEntry),
    iob_inputs: Schema.Any,
    basalprofile: Schema.Array(BasalSchedule),
    retrospective: Schema.optional(Schema.Boolean),
    carbs: Schema.Array(CarbEntry),
    temptargets: Schema.Array(TempTarget.TempTarget),
    deviations: Schema.optional(Schema.Number),
})

type Inputs = typeof Inputs.Type

export default function generate(inputs: unknown) {
    return detectSensitivity(Schema.decodeUnknownSync(Inputs)(inputs))
}

export function detectSensitivity(inputs: Inputs) {
    //console.error(inputs.glucose_data[0]);
    const glucose_data = reduceWithGlucoseAndDate(inputs.glucose_data)
    //console.error(glucose_data[0]);
    const iob_inputs = inputs.iob_inputs
    const basalprofile = inputs.basalprofile
    const profile = inputs.iob_inputs.profile

    let lastSiteChange = new Date(new Date().getTime() - 24 * 60 * 60 * 1000)
    // use last 24h worth of data by default
    if (inputs.retrospective) {
        const firstDate = new Date(glucose_data[0].date)
        if (!firstDate) {
            throw new Error('Unable to find glucose date for first item')
        }
        lastSiteChange = new Date(firstDate.getTime() - 24 * 60 * 60 * 1000)
    }

    if (inputs.iob_inputs.profile.rewind_resets_autosens === true) {
        // scan through pumphistory and set lastSiteChange to the time of the last pump rewind event
        // if not present, leave lastSiteChange unchanged at 24h ago.
        const history = inputs.iob_inputs.history
        for (let h = 1; h < history.length; ++h) {
            if (!history[h]._type || history[h]._type !== 'Rewind') {
                //process.stderr.write("-");
                continue
            }
            if (history[h].timestamp) {
                lastSiteChange = new Date(history[h].timestamp)
                console.error('Setting lastSiteChange to', lastSiteChange, 'using timestamp', history[h].timestamp)
                break
            }
        }
    }

    // get treatments from pumphistory once, not every time we get_iob()
    const treatments = findInsulin(inputs.iob_inputs)

    const mealinputs = {
        history: inputs.iob_inputs.history,
        profile: profile,
        carbs: inputs.carbs,
        glucose: inputs.glucose_data,
        //, prepped_glucose: prepped_glucose_data
    }
    const meals = A.sort(findMeals(mealinputs), MealTreatment.Order)
    //console.error(meals);

    const avgDeltas = []
    const bgis = []
    const deviations = []
    //let deviationSum = 0
    const bucketed_data = []
    glucose_data.reverse()
    bucketed_data[0] = glucose_data[0]
    //console.error(bucketed_data[0]);
    let j = 0
    // go through the meal treatments and remove any that are older than the oldest glucose value
    //console.error(meals);
    for (let i = 1; i < glucose_data.length; ++i) {
        let bgTime
        let lastbgTime
        const entry = glucose_data[i]
        const previous = glucose_data[i - 1]
        if (entry.display_time) {
            bgTime = new Date(entry.display_time.replace('T', ' '))
        } else if (entry.dateString) {
            bgTime = new Date(entry.dateString)
        } else if (entry.xDrip_started_at) {
            continue
        } else {
            console.error('Could not determine BG time')
            continue
        }
        if (previous.display_time) {
            lastbgTime = new Date(previous.display_time.replace('T', ' '))
        } else if (previous.dateString) {
            lastbgTime = new Date(previous.dateString)
        } else if (bucketed_data[0].display_time) {
            lastbgTime = new Date(bucketed_data[0].display_time.replace('T', ' '))
        } else if (glucose_data[i - 1].xDrip_started_at) {
            continue
        } else {
            console.error('Could not determine last BG time')
            continue
        }
        if (entry.glucose < 39 || glucose_data[i - 1].glucose < 39) {
            //console.error("skipping:",glucose_data[i].glucose,glucose_data[i-1].glucose);
            continue
        }
        // only consider BGs since lastSiteChange
        if (lastSiteChange) {
            const hoursSinceSiteChange = (bgTime.getTime() - lastSiteChange.getTime()) / (60 * 60 * 1000)
            if (hoursSinceSiteChange < 0) {
                //console.error(hoursSinceSiteChange, bgTime, lastSiteChange);
                continue
            }
        }
        const elapsed_minutes = (bgTime.getTime() - lastbgTime.getTime()) / (60 * 1000)
        if (Math.abs(elapsed_minutes) > 2) {
            j++
            bucketed_data[j] = entry
            bucketed_data[j].date = bgTime.getTime()
            //console.error(elapsed_minutes, bucketed_data[j].glucose, glucose_data[i].glucose);
        } else {
            bucketed_data[j].glucose = (bucketed_data[j].glucose + glucose_data[i].glucose) / 2
            //console.error(bucketed_data[j].glucose, glucose_data[i].glucose);
        }
    }
    bucketed_data.shift()
    //console.error(bucketed_data[0]);
    for (let i = meals.length - 1; i > 0; --i) {
        const treatment = meals[i]
        //console.error(treatment);
        if (treatment) {
            const treatmentDate = new Date(tz(treatment.timestamp))
            const treatmentTime = treatmentDate.getTime()
            const glucoseDatum = bucketed_data[0]
            //console.error(glucoseDatum);
            if (!glucoseDatum || !glucoseDatum.date) {
                //console.error("No date found on: ",glucoseDatum);
                continue
            }
            const BGDate = new Date(glucoseDatum.date)
            const BGTime = BGDate.getTime()
            if (treatmentTime < BGTime) {
                //console.error("Removing old meal: ",treatmentDate);
                meals.splice(i, 1)
            }
        }
    }
    let absorbing = 0
    let uam = 0 // unannounced meal
    let mealCOB = 0
    let mealCarbs = 0
    let mealStartCounter = 999
    let type = ''
    let lastIsfResult: ISFSensitivity | null = null
    //console.error(bucketed_data);
    for (let i = 3; i < bucketed_data.length; ++i) {
        const bucketed = bucketed_data[i]
        const bgTime = new Date(bucketed.date!)
        const [sens, isf_res] = isfLookup(profile.isfProfile, bgTime, lastIsfResult)
        lastIsfResult = isf_res as ISFSensitivity | null
        //console.error(bgTime , bucketed_data[i].glucose);
        let bg
        let avgDelta
        let delta
        let last_bg
        let old_bg
        if (typeof bucketed_data[i].glucose !== 'undefined') {
            bg = bucketed_data[i].glucose
            last_bg = bucketed_data[i - 1].glucose
            old_bg = bucketed_data[i - 3].glucose
            if (
                isNaN(bg) ||
                !bg ||
                bg < 40 ||
                isNaN(old_bg) ||
                !old_bg ||
                old_bg < 40 ||
                isNaN(last_bg) ||
                !last_bg ||
                last_bg < 40
            ) {
                process.stderr.write('!')
                continue
            }
            avgDelta = (bg - old_bg) / 3
            delta = bg - last_bg
        } else {
            console.error('Could not find glucose data')
            continue
        }

        avgDelta = Math.round(avgDelta * 100) / 100
        iob_inputs.clock = bgTime
        iob_inputs.profile.current_basal = basalLookup(basalprofile, bgTime)
        // make sure autosens doesn't use temptarget-adjusted insulin calculations
        iob_inputs.profile.temptargetSet = false
        //console.log(JSON.stringify(iob_inputs.profile));
        //console.error("Before: ", new Date().getTime());
        const iob = getIob(iob_inputs, true, treatments)[0]
        //console.error("After: ", new Date().getTime());
        //console.log(JSON.stringify(iob));

        const bgi = Math.round(-iob.activity * sens * 5 * 100) / 100
        //bgi = bgi.toFixed(2)
        //console.error(delta);
        let deviation
        if (isNaN(delta)) {
            console.error('Bad delta: ', delta, bg, last_bg, old_bg)
            continue
        } else {
            deviation = delta - bgi
        }
        //if (!deviation) { console.error(deviation, delta, bgi); }
        // set positive deviations to zero if BG is below 80
        if (bg < 80 && deviation > 0) {
            deviation = 0
        }
        deviation = Math.round(deviation * 100) / 100

        let glucoseDatum: GlucoseEntry & {
            glucose: number
            mealCarbs?: number
        } = bucketed_data[i]
        //console.error(glucoseDatum);
        const BGDate = new Date(glucoseDatum.date!)
        const BGTime = BGDate.getTime()
        // As we're processing each data point, go through the treatment.carbs and see if any of them are older than
        // the current BG data point.  If so, add those carbs to COB.
        const treatment = meals[meals.length - 1]
        if (treatment) {
            const treatmentDate = new Date(tz(treatment.timestamp))
            const treatmentTime = treatmentDate.getTime()
            if (treatmentTime < BGTime) {
                if (treatment.carbs >= 1) {
                    //console.error(treatmentDate, treatmentTime, BGTime, BGTime-treatmentTime);
                    mealCOB += treatment.carbs
                    mealCarbs += treatment.carbs
                    const displayCOB = Math.round(mealCOB)
                    //console.error(displayCOB, mealCOB, treatment.carbs);
                    process.stderr.write(`${displayCOB.toString()}g`)
                }
                meals.pop()
            }
        }

        // calculate carb absorption for that 5m interval using the deviation.
        if (mealCOB > 0) {
            //var profile = profileData;
            const ci = Math.max(deviation, profile.min_5m_carbimpact)
            const absorbed = (ci * profile.carb_ratio) / sens
            if (absorbed) {
                mealCOB = Math.max(0, mealCOB - absorbed)
            } else {
                console.error(absorbed, ci, profile.carb_ratio, sens, deviation, profile.min_5m_carbimpact)
            }
        }

        // If mealCOB is zero but all deviations since hitting COB=0 are positive, exclude from autosens
        //console.error(mealCOB, absorbing, mealCarbs);
        if (mealCOB > 0 || absorbing || mealCarbs > 0) {
            if (deviation > 0) {
                absorbing = 1
            } else {
                absorbing = 0
            }
            // stop excluding positive deviations as soon as mealCOB=0 if meal has been absorbing for >5h
            if (mealStartCounter > 60 && mealCOB < 0.5) {
                const displayCOB = Math.round(mealCOB)
                process.stderr.write(`${displayCOB.toString()}g`)
                absorbing = 0
            }
            if (!absorbing && mealCOB < 0.5) {
                mealCarbs = 0
            }
            // check previous "type" value, and if it wasn't csf, set a mealAbsorption start flag
            //console.error(type);
            if (type !== 'csf') {
                process.stderr.write('(')
                mealStartCounter = 0
                //glucoseDatum.mealAbsorption = "start";
                //console.error(glucoseDatum.mealAbsorption,"carb absorption");
            }
            mealStartCounter++
            type = 'csf'
            glucoseDatum = {
                ...glucoseDatum,
                mealCarbs,
            }
            //if (i == 0) { glucoseDatum.mealAbsorption = "end"; }
            //CSFGlucoseData.push(glucoseDatum);
        } else {
            // check previous "type" value, and if it was csf, set a mealAbsorption end flag
            if (type === 'csf') {
                process.stderr.write(')')
                //CSFGlucoseData[CSFGlucoseData.length-1].mealAbsorption = "end";
                //console.error(CSFGlucoseData[CSFGlucoseData.length-1].mealAbsorption,"carb absorption");
            }

            const currentBasal = iob_inputs.profile.current_basal
            // always exclude the first 45m after each carb entry using mealStartCounter
            //if (iob.iob > currentBasal || uam ) {
            if ((!inputs.retrospective && iob.iob > 2 * currentBasal) || uam || mealStartCounter < 9) {
                mealStartCounter++
                if (deviation > 0) {
                    uam = 1
                } else {
                    uam = 0
                }
                if (type !== 'uam') {
                    process.stderr.write('u(')
                    //glucoseDatum.uamAbsorption = "start";
                    //console.error(glucoseDatum.uamAbsorption,"uannnounced meal absorption");
                }
                //console.error(mealStartCounter);
                type = 'uam'
            } else {
                if (type === 'uam') {
                    process.stderr.write(')')
                    //console.error("end unannounced meal absorption");
                }
                type = 'non-meal'
            }
        }

        // Exclude meal-related deviations (carb absorption) from autosens
        if (type === 'non-meal') {
            if (deviation > 0) {
                //process.stderr.write(" "+bg.toString());
                process.stderr.write('+')
            } else if (deviation === 0) {
                process.stderr.write('=')
            } else {
                //process.stderr.write(" "+bg.toString());
                process.stderr.write('-')
            }
            avgDeltas.push(avgDelta)
            bgis.push(bgi)
            deviations.push(deviation)
            //deviationSum += parseFloat(deviation)
        } else {
            process.stderr.write('x')
        }
        // add an extra negative deviation if a high temptarget is running and exercise mode is set
        if (profile.high_temptarget_raises_sensitivity === true || profile.exercise_mode === true) {
            const tempTarget = tempTargetRunning(inputs.temptargets, bgTime)
            if (tempTarget) {
                //console.error(tempTarget)
            }
            if (tempTarget > 100) {
                // for a 110 temptarget, add a -0.5 deviation, for 160 add -3
                const tempDeviation = -(tempTarget - 100) / 20
                process.stderr.write('-')
                //console.error(tempDeviation)
                deviations.push(tempDeviation)
            }
        }

        const minutes = bgTime.getMinutes()
        const hours = bgTime.getHours()
        if (minutes >= 0 && minutes < 5) {
            //console.error(bgTime);
            process.stderr.write(`${hours.toString()}h`)
            // add one neutral deviation every 2 hours to help decay over long exclusion periods
            if (hours % 2 === 0) {
                deviations.push(0)
                process.stderr.write('=')
            }
        }
        let lookback = inputs.deviations
        if (!lookback) {
            lookback = 96
        }
        // only keep the last 96 non-excluded data points (8h+ for any exclusions)
        if (deviations.length > lookback) {
            deviations.shift()
        }
    }
    //console.error("");
    process.stderr.write(' ')
    //console.log(JSON.stringify(avgDeltas));
    //console.log(JSON.stringify(bgis));
    // when we have less than 8h worth of deviation data, add up to 90m of zero deviations
    // this dampens any large sensitivity changes detected based on too little data, without ignoring them completely
    console.error('')
    console.error('Using most recent', deviations.length, 'deviations since', lastSiteChange)
    if (deviations.length < 96) {
        const pad = Math.round((1 - deviations.length / 96) * 18)
        console.error('Adding', pad, 'more zero deviations')
        for (let d = 0; d < pad; d++) {
            //process.stderr.write(".");
            deviations.push(0)
        }
    }
    avgDeltas.sort((a, b) => {
        return a - b
    })
    bgis.sort((a, b) => {
        return a - b
    })
    deviations.sort((a, b) => {
        return a - b
    })
    for (let i = 0.9; i > 0.1; i = i - 0.01) {
        //console.error("p="+i.toFixed(2)+": "+percentile(avgDeltas, i).toFixed(2)+", "+percentile(bgis, i).toFixed(2)+", "+percentile(deviations, i).toFixed(2));
        if (percentile(deviations, i + 0.01) >= 0 && percentile(deviations, i) < 0) {
            //console.error("p="+i.toFixed(2)+": "+percentile(avgDeltas, i).toFixed(2)+", "+percentile(bgis, i).toFixed(2)+", "+percentile(deviations, i).toFixed(2));
            const lessThanZero = Math.round(100 * i)
            console.error(`${lessThanZero}% of non-meal deviations negative (>50% = sensitivity)`)
        }
        if (percentile(deviations, i + 0.01) > 0 && percentile(deviations, i) <= 0) {
            //console.error("p="+i.toFixed(2)+": "+percentile(avgDeltas, i).toFixed(2)+", "+percentile(bgis, i).toFixed(2)+", "+percentile(deviations, i).toFixed(2));
            const greaterThanZero = 100 - Math.round(100 * i)
            console.error(`${greaterThanZero}% of non-meal deviations positive (>50% = resistance)`)
        }
    }
    const pSensitive = percentile(deviations, 0.5)
    const pResistant = percentile(deviations, 0.5)

    //const average = deviationSum / deviations.length
    //console.error("Mean deviation: "+average.toFixed(2));

    const squareDeviations = deviations.reduce((acc, dev) => {
        const dev_f = dev
        return acc + dev_f * dev_f
    }, 0)
    const rmsDev = Math.sqrt(squareDeviations / deviations.length)
    console.error(`RMS deviation: ${rmsDev.toFixed(2)}`)

    let basalOff = 0

    if (pSensitive < 0) {
        // sensitive
        basalOff = (pSensitive * (60 / 5)) / profile.sens
        process.stderr.write('Insulin sensitivity detected: ')
    } else if (pResistant > 0) {
        // resistant
        basalOff = (pResistant * (60 / 5)) / profile.sens
        process.stderr.write('Insulin resistance detected: ')
    } else {
        console.error('Sensitivity normal.')
    }
    let ratio = 1 + basalOff / profile.max_daily_basal
    //console.error(basalOff, profile.max_daily_basal, ratio);

    // don't adjust more than 1.2x by default (set in preferences.json)
    const rawRatio = ratio
    ratio = Math.max(ratio, profile.autosens_min)
    ratio = Math.min(ratio, profile.autosens_max)

    if (ratio !== rawRatio) {
        console.error(`Ratio limited from ${rawRatio} to ${ratio}`)
    }

    ratio = Math.round(ratio * 100) / 100
    const newisf = Math.round(profile.sens / ratio)
    //console.error(profile, newisf, ratio);
    console.error(`ISF adjusted from ${profile.sens} to ${newisf}`)
    //console.error("Basal adjustment "+basalOff.toFixed(2)+"U/hr");
    //console.error("Ratio: "+ratio*100+"%: new ISF: "+newisf.toFixed(1)+"mg/dL/U");
    return {
        ratio: ratio,
        newisf: newisf,
    }
}

function tempTargetRunning(temptargets: ReadonlyArray<TempTarget.TempTarget>, time: Date) {
    // sort tempTargets by date so we can process most recent first
    const temptargets_data = A.sort(temptargets, TempTarget.Order)
    //console.error(temptargets_data);
    //console.error(time);
    for (let i = 0; i < temptargets_data.length; i++) {
        const start = new Date(temptargets_data[i].created_at)
        //console.error(start);
        const expires = new Date(start.getTime() + temptargets_data[i].duration * 60 * 1000)
        //console.error(expires);
        if (time >= new Date(temptargets_data[i].created_at) && temptargets_data[i].duration === 0) {
            // cancel temp targets
            //console.error(temptargets_data[i]);
            return 0
        } else if (time >= new Date(temptargets_data[i].created_at) && time < expires) {
            //console.error(temptargets_data[i]);
            const tempTarget = (temptargets_data[i].targetTop + temptargets_data[i].targetBottom) / 2
            //console.error(tempTarget);
            return tempTarget
        }
    }

    return 0
}
