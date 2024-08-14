import { getIob } from '../iob'
import type { Input as IOBInput } from '../iob/Input'
import { findInsulin } from '../iob/history'
import * as basal from '../profile/basal'
import { isfLookup } from '../profile/isf'
import type { BasalSchedule } from '../types/BasalSchedule'
import { reduceWithGlucoseAndDate, type GlucoseEntry } from '../types/GlucoseEntry'

export interface DetectCOBInput {
    glucose_data: ReadonlyArray<GlucoseEntry>
    iob_inputs: IOBInput
    basalprofile?: ReadonlyArray<BasalSchedule>
    mealTime: number
    ciTime?: number
}

/**
 * @todo: does it works with profile.carb_ratio === undefined?
 */
export function detectCarbAbsorption(inputs: DetectCOBInput) {
    const glucose_data = reduceWithGlucoseAndDate(inputs.glucose_data)

    let iob_inputs = inputs.iob_inputs
    const basalprofile = inputs.basalprofile
    /* TODO why does declaring profile break tests-command-behavior.tests.sh?
       because it is a global variable used in other places.*/
    const profile = inputs.iob_inputs.profile
    const mealTime = new Date(inputs.mealTime)
    const ciTime = inputs.ciTime ? new Date(inputs.ciTime) : undefined

    //console.error(mealTime, ciTime);

    // get treatments from pumphistory once, not every time we get_iob()
    const treatments = findInsulin(inputs.iob_inputs)

    if (!glucose_data.length) {
        // @todo: return something empty
    }

    let carbsAbsorbed = 0
    const bucketed_data: Array<{ date: number; glucose: number }> = glucose_data.slice(0, 1)
    let j = 0
    let foundPreMealBG = false
    let lastbgi = 0

    if (!glucose_data[0].glucose || glucose_data[0].glucose < 39) {
        lastbgi = -1
    }

    for (let i = 1; i < glucose_data.length; ++i) {
        const currentGlucose = glucose_data[i]
        const bgTime = new Date(currentGlucose.date)
        let lastbgTime
        if (currentGlucose.glucose < 39) {
            //console.error("skipping:",glucose_data[i].glucose);
            continue
        }
        // only consider BGs for 6h after a meal for calculating COB
        const hoursAfterMeal = (bgTime.getTime() - mealTime.getTime()) / (60 * 60 * 1000)
        if (hoursAfterMeal > 6 || foundPreMealBG) {
            continue
        } else if (hoursAfterMeal < 0) {
            //console.error("Found pre-meal BG:",glucose_data[i].glucose, bgTime, Math.round(hoursAfterMeal*100)/100);
            foundPreMealBG = true
        }
        //console.error(glucose_data[i].glucose, bgTime, Math.round(hoursAfterMeal*100)/100, bucketed_data[bucketed_data.length-1].display_time);
        // only consider last ~45m of data in CI mode
        // this allows us to calculate deviations for the last ~30m
        if (typeof ciTime !== 'undefined') {
            const hoursAgo = (ciTime.getTime() - bgTime.getTime()) / (45 * 60 * 1000)
            if (hoursAgo > 1 || hoursAgo < 0) {
                continue
            }
        }
        const lastBucketedData = bucketed_data[bucketed_data.length - 1]
        lastbgTime = new Date(lastBucketedData.date)
        let elapsed_minutes = (bgTime.getTime() - lastbgTime.getTime()) / (60 * 1000)
        //console.error(bgTime, lastbgTime, elapsed_minutes);
        if (Math.abs(elapsed_minutes) > 8) {
            // interpolate missing data points
            let lastbg = glucose_data[lastbgi].glucose
            // cap interpolation at a maximum of 4h
            elapsed_minutes = Math.min(240, Math.abs(elapsed_minutes))
            //console.error(elapsed_minutes);
            while (elapsed_minutes > 5) {
                const previousbgTime: Date = new Date(lastbgTime.getTime() - 5 * 60 * 1000)
                j++

                const gapDelta = glucose_data[i].glucose - lastbg
                const previousbg = lastbg + (5 / elapsed_minutes) * gapDelta
                bucketed_data[j] = {
                    date: previousbgTime.getTime(),
                    glucose: Math.round(previousbg),
                }

                elapsed_minutes = elapsed_minutes - 5
                lastbg = previousbg
                lastbgTime = new Date(previousbgTime)
            }
        } else if (Math.abs(elapsed_minutes) > 2) {
            j++
            bucketed_data[j] = glucose_data[i]
            bucketed_data[j].date = bgTime.getTime()
        } else {
            bucketed_data[j].glucose = (bucketed_data[j].glucose + glucose_data[i].glucose) / 2
        }

        lastbgi = i
        //console.error(bucketed_data[j].date)
    }
    let currentDeviation = 0
    let slopeFromMaxDeviation = 0
    let slopeFromMinDeviation = 999
    let maxDeviation = 0
    let minDeviation = 999
    const allDeviations = []
    //console.error(bucketed_data);
    let lastIsfResult = null
    if (!profile.isfProfile) {
        console.error('No isfProfile found in Profile')
        throw new TypeError('No isfProfile found in Profile')
    }
    for (let i = 0; i < bucketed_data.length - 3; ++i) {
        const bgTime = new Date(bucketed_data[i].date)

        let sens = null
        ;[sens, lastIsfResult] = isfLookup(profile.isfProfile, bgTime, lastIsfResult)

        //console.error(bgTime , bucketed_data[i].glucose, bucketed_data[i].date);
        let bg
        let avgDelta
        let delta
        if (typeof bucketed_data[i].glucose !== 'undefined') {
            bg = bucketed_data[i].glucose
            if (bg < 39 || bucketed_data[i + 3].glucose < 39) {
                process.stderr.write('!')
                continue
            }
            avgDelta = Math.round(((bg - bucketed_data[i + 3].glucose) / 3) * 100) / 100
            delta = bg - bucketed_data[i + 1].glucose
        } else {
            console.error('Could not find glucose data')
            continue
        }

        iob_inputs = {
            ...iob_inputs,
            clock: bgTime.toISOString(),
        }
        const current_basal = basal.basalLookup(basalprofile || [], bgTime)
        if (!current_basal) {
            continue
        }
        const newIobInputs = {
            ...iob_inputs,
            profile: {
                ...iob_inputs.profile,
                current_basal,
            },
        }

        //console.log(JSON.stringify(iob_inputs.profile));
        //console.error("Before: ", new Date().getTime());
        const iob = getIob(newIobInputs, true, treatments)[0]
        //console.error("After: ", new Date().getTime());
        //console.error(JSON.stringify(iob));

        const bgi = Math.round(-iob.activity * sens * 5 * 100) / 100
        //console.error(delta);
        const deviation = Math.round((delta - bgi) * 100) / 100
        //if (deviation < 0 && deviation > -2) { console.error("BG: "+bg+", avgDelta: "+avgDelta+", BGI: "+bgi+", deviation: "+deviation); }
        // calculate the deviation right now, for use in min_5m
        if (i === 0) {
            currentDeviation = Math.round((avgDelta - bgi) * 1000) / 1000
            if (ciTime && ciTime > bgTime) {
                //console.error("currentDeviation:",currentDeviation,avgDelta,bgi);
                allDeviations.push(Math.round(currentDeviation))
            }
            if (currentDeviation / 2 > profile.min_5m_carbimpact) {
                //console.error("currentDeviation",currentDeviation,"/2 > min_5m_carbimpact",profile.min_5m_carbimpact);
            }
        } else if (ciTime && ciTime > bgTime) {
            const avgDeviation = Math.round((avgDelta - bgi) * 1000) / 1000
            const deviationSlope =
                ((avgDeviation - currentDeviation) / (bgTime.getTime() - ciTime.getTime())) * 1000 * 60 * 5
            //console.error(avgDeviation,currentDeviation,bgTime,ciTime)
            if (avgDeviation > maxDeviation) {
                slopeFromMaxDeviation = Math.min(0, deviationSlope)
                maxDeviation = avgDeviation
            }
            if (avgDeviation < minDeviation) {
                slopeFromMinDeviation = Math.max(0, deviationSlope)
                minDeviation = avgDeviation
            }

            //console.error("Deviations:",avgDeviation, avgDelta,bgi,bgTime);
            allDeviations.push(Math.round(avgDeviation))
            //console.error(allDeviations);
        }

        // if bgTime is more recent than mealTime
        if (bgTime > mealTime) {
            // figure out how many carbs that represents
            // if currentDeviation is > 2 * min_5m_carbimpact, assume currentDeviation/2 worth of carbs were absorbed
            // but always assume at least profile.min_5m_carbimpact (3mg/dL/5m by default) absorption
            const ci = Math.max(deviation, currentDeviation / 2, profile.min_5m_carbimpact)
            const absorbed = profile.carb_ratio ? (ci * profile.carb_ratio) / sens : 0
            // and add that to the running total carbsAbsorbed
            //console.error("carbsAbsorbed:",carbsAbsorbed,"absorbed:",absorbed,"bgTime:",bgTime,"BG:",bucketed_data[i].glucose)
            carbsAbsorbed += absorbed
        }
    }
    if (maxDeviation > 0) {
        //console.error("currentDeviation:",currentDeviation,"maxDeviation:",maxDeviation,"slopeFromMaxDeviation:",slopeFromMaxDeviation);
    }

    return {
        carbsAbsorbed: carbsAbsorbed,
        currentDeviation: currentDeviation,
        maxDeviation: maxDeviation,
        minDeviation: minDeviation,
        slopeFromMaxDeviation: slopeFromMaxDeviation,
        slopeFromMinDeviation: slopeFromMinDeviation,
        allDeviations: allDeviations,
    }
}

export default detectCarbAbsorption
