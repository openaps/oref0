import { flow, pipe } from 'effect'
import * as A from 'effect/Array'
import * as Option from 'effect/Option'
import * as O from 'effect/Order'
import { getIob } from '../iob'
import { findInsulin } from '../iob/history'
import type { MealTreatment } from '../meal/MealTreatment'
import { basalLookup } from '../profile/basal'
import { isfLookup } from '../profile/isf'
import type { BasalSchedule } from '../types/BasalSchedule'
import * as GlucoseEntry from '../types/GlucoseEntry'
import type { ISFSensitivity } from '../types/ISFSensitivity'
import type { NightscoutTreatment } from '../types/NightscoutTreatment'
import type { Profile } from '../types/Profile'
import { insulinDosed } from './dosed'

interface Input {
    treatments: ReadonlyArray<MealTreatment>
    profile: Profile
    pumpHistory: ReadonlyArray<NightscoutTreatment>
    glucose: ReadonlyArray<GlucoseEntry.GlucoseEntry>
    basalprofile: ReadonlyArray<BasalSchedule>
    pumpbasalprofile: ReadonlyArray<BasalSchedule>
    categorize_uam_as_basal: boolean
}

type CSFUAMGlucoseData = GlucoseEntry.GlucoseEntry & {
    glucose: number
    date: number
    dateString: string
    avgDelta: number
    BGI: number
    deviation: number
    mealCarbs: number
    uamAbsorption?: string | undefined
    mealAbsorption?: string | undefined
}

export function categorizeBGDatums(opts: Input) {
    // this sorts the treatments collection in order.
    let treatments = A.sort(
        opts.treatments,
        O.mapInput<Date, MealTreatment>(O.Date, a => new Date(a.timestamp))
    )
    const profile = opts.profile
    const pumpHistory = opts.pumpHistory

    if (!profile.isfProfile) {
        throw new Error('ISF profile not set')
    }

    if (!profile.carb_ratio) {
        throw new Error('Carb ration not set')
    }

    const glucoseData = pipe(
        opts.glucose || [],
        A.filterMap(
            flow(
                GlucoseEntry.setGlucoseField,
                GlucoseEntry.setDateFields,
                GlucoseEntry.filterWithGlucose,
                Option.filter(({ glucose }) => glucose > 39)
            )
        ),
        A.sort(O.reverse(GlucoseEntry.Order))
    )

    if (!treatments.length) {
        return undefined
    }

    //console.error(glucoseData);
    let CSFGlucoseData: CSFUAMGlucoseData[] = []
    let ISFGlucoseData: CSFUAMGlucoseData[] = []
    let basalGlucoseData = []
    const UAMGlucoseData: CSFUAMGlucoseData[] = []
    let CRData = []

    const bucketedData = [glucoseData[0]]
    let j = 0
    let k = 0 // index of first value used by bucket
    //for loop to validate and bucket the data
    for (let i = 1; i < glucoseData.length; ++i) {
        const current = glucoseData[i]
        const BGTime = new Date(current.dateString)
        const lastBGTime = new Date(glucoseData[k].dateString)
        const elapsedMinutes = (BGTime.getTime() - lastBGTime.getTime()) / (60 * 1000)

        if (Math.abs(elapsedMinutes) >= 2) {
            j++ // move to next bucket
            k = i // store index of first value used by bucket
            bucketedData[j] = glucoseData[i]
        } else {
            // average all readings within time deadband
            const glucoseTotal = glucoseData.slice(k, i + 1).reduce((total, entry) => total + entry.glucose, 0)
            bucketedData[j] = {
                ...bucketedData[j],
                glucose: glucoseTotal / (i - k + 1),
            }
        }
    }
    //console.error(bucketedData);
    //console.error(bucketedData[bucketedData.length-1]);
    // go through the treatments and remove any that are older than the oldest glucose value
    //console.error(treatments);
    const lastBucked = bucketedData[bucketedData.length - 1]
    if (lastBucked) {
        treatments = A.filter(
            treatments,
            treatment => new Date(treatment.timestamp).getTime() >= new Date(lastBucked.dateString).getTime()
        )
    }
    //console.error(treatments);
    let calculatingCR = false
    let absorbing = 0
    let uam = 0 // unannounced meal
    let mealCOB = 0
    let mealCarbs = 0
    let CRCarbs = 0
    let type = ''
    // main for loop
    const fullHistory = pumpHistory
    let newProfile = {
        ...profile,
    }
    let lastIsfResult: ISFSensitivity | null = null
    let CRInitialCarbTime
    let CRInitialIOB
    let CRInitialBG
    for (let i = bucketedData.length - 5; i > 0; --i) {
        const current = bucketedData[i]
        const glucose = current.glucose
        //console.error(glucoseDatum);
        const BGDate = GlucoseEntry.getDate(current)
        const BGTime = BGDate.getTime()
        // As we're processing each data point, go through the treatment.carbs and see if any of them are older than
        // the current BG data point.  If so, add those carbs to COB.
        const treatment = treatments[treatments.length - 1]
        let myCarbs = 0
        if (treatment) {
            const treatmentDate = new Date(treatment.timestamp)
            const treatmentTime = treatmentDate.getTime()
            //console.error(treatmentDate);
            if (treatmentTime < BGTime) {
                if (treatment.carbs >= 1) {
                    mealCOB += treatment.carbs
                    mealCarbs += treatment.carbs
                    myCarbs = treatment.carbs
                }
                treatments = A.remove(treatments, treatments.length - 1)
            }
        }

        // TODO: re-implement interpolation to avoid issues here with gaps
        // calculate avgDelta as last 4 datapoints to better catch more rises after COB hits zero
        const BG = glucose
        if (BG < 40 || bucketedData[i + 4].glucose < 40) {
            //process.stderr.write("!");
            continue
        }
        const delta = BG - bucketedData[i + 1].glucose
        const avgDelta = Math.round(((BG - bucketedData[i + 4].glucose) / 4) * 100) / 100

        //sens = ISF
        let sens
        ;[sens, lastIsfResult] = isfLookup(profile.isfProfile, BGDate, lastIsfResult)
        // trim down IOBInputs.history to just the data for 6h prior to BGDate
        //console.error(IOBInputs.history[0].created_at);
        const newHistory = []
        for (let h = 0; h < fullHistory.length; h++) {
            const hDate = new Date(fullHistory[h].created_at)
            //console.error(fullHistory[i].created_at, hDate, BGDate, BGDate-hDate);
            //if (h == 0 || h == fullHistory.length - 1) {
            //console.error(hDate, BGDate, hDate-BGDate)
            //}
            if (BGDate.getTime() - hDate.getTime() < 6 * 60 * 60 * 1000 && BGDate.getTime() - hDate.getTime() > 0) {
                //process.stderr.write("i");
                //console.error(hDate);
                newHistory.push(fullHistory[h])
            }
        }
        // process.stderr.write("" + newHistory.length + " ");
        //console.error(newHistory[0].created_at,newHistory[newHistory.length-1].created_at,newHistory.length);

        // for IOB calculations, use the average of the last 4 hours' basals to help convergence;
        // this helps since the basal this hour could be different from previous, especially if with autotune they start to diverge.
        // use the pumpbasalprofile to properly calculate IOB during periods where no temp basal is set
        const currentPumpBasal = basalLookup(opts.pumpbasalprofile, BGDate)
        const BGDate1hAgo = new Date(BGTime - 1 * 60 * 60 * 1000)
        const BGDate2hAgo = new Date(BGTime - 2 * 60 * 60 * 1000)
        const BGDate3hAgo = new Date(BGTime - 3 * 60 * 60 * 1000)
        const basal1hAgo = basalLookup(opts.pumpbasalprofile, BGDate1hAgo)
        const basal2hAgo = basalLookup(opts.pumpbasalprofile, BGDate2hAgo)
        const basal3hAgo = basalLookup(opts.pumpbasalprofile, BGDate3hAgo)
        const sum = [currentPumpBasal, basal1hAgo, basal2hAgo, basal3hAgo].reduce((a, b) => {
            return a + b
        })

        newProfile = {
            ...newProfile,
            current_basal: Math.round((sum / 4) * 1000) / 1000,
        }
        // this is the current autotuned basal, used for everything else besides IOB calculations
        const currentBasal = basalLookup(opts.basalprofile, BGDate)

        //console.error(currentBasal,basal1hAgo,basal2hAgo,basal3hAgo,IOBInputs.profile.currentBasal);
        // basalBGI is BGI of basal insulin activity.
        const basalBGI = Math.round(((currentBasal * sens) / 60) * 5 * 100) / 100 // U/hr * mg/dL/U * 1 hr / 60 minutes * 5 = mg/dL/5m
        //console.log(JSON.stringify(IOBInputs.profile));
        // call iob since calculated elsewhere
        const iob = getIob({
            profile: newProfile,
            history: newHistory,
            clock: BGDate.toISOString(),
        })[0]
        //console.error(JSON.stringify(iob));

        // activity times ISF times 5 minutes is BGI
        const BGI = Math.round(-iob.activity * sens * 5 * 100) / 100
        // datum = one glucose data point (being prepped to store in output)

        // calculating deviation
        let deviation = Math.round((avgDelta - BGI) * 100) / 100
        const dev5m = Math.round((delta - BGI) * 100) / 100
        //console.error(deviation,avgDelta,BG,bucketedData[i].glucose);

        // set positive deviations to zero if BG is below 80
        if (BG < 80 && deviation > 0) {
            deviation = 0
        }

        // Then, calculate carb absorption for that 5m interval using the deviation.
        if (mealCOB > 0) {
            const ci = Math.max(deviation, profile.min_5m_carbimpact)
            const absorbed = (ci * profile.carb_ratio) / sens
            // Store the COB, and use it as the starting point for the next data point.
            mealCOB = Math.max(0, mealCOB - absorbed)
        }

        // Calculate carb ratio (CR) independently of CSF and ISF
        // Use the time period from meal bolus/carbs until COB is zero and IOB is < currentBasal/2
        // For now, if another meal IOB/COB stacks on top of it, consider them together
        // Compare beginning and ending BGs, and calculate how much more/less insulin is needed to neutralize
        // Use entered carbs vs. starting IOB + delivered insulin + needed-at-end insulin to directly calculate CR.

        if (mealCOB > 0 || calculatingCR) {
            // set initial values when we first see COB
            CRCarbs += myCarbs

            if (!calculatingCR) {
                CRInitialIOB = iob.iob
                CRInitialBG = glucose
                CRInitialCarbTime = GlucoseEntry.getDate(current)
                console.error(
                    'CRInitialIOB:',
                    CRInitialIOB,
                    'CRInitialBG:',
                    CRInitialBG,
                    'CRInitialCarbTime:',
                    CRInitialCarbTime
                )
            }
            // keep calculatingCR as long as we have COB or enough IOB
            if (mealCOB > 0 && i > 1) {
                calculatingCR = true
            } else if (iob.iob > currentBasal / 2 && i > 1) {
                calculatingCR = true
                // when COB=0 and IOB drops low enough, record end values and be done calculatingCR
            } else {
                const CREndIOB = iob.iob
                const CREndBG = glucose
                const CREndTime = GlucoseEntry.getDate(current)
                console.error('CREndIOB:', CREndIOB, 'CREndBG:', CREndBG, 'CREndTime:', CREndTime)
                const CRDatum = {
                    CRInitialIOB: CRInitialIOB,
                    CRInitialBG: CRInitialBG,
                    CRInitialCarbTime: CRInitialCarbTime,
                    CREndIOB: CREndIOB,
                    CREndBG: CREndBG,
                    CREndTime: CREndTime,
                    CRCarbs: CRCarbs,
                }
                //console.error(CRDatum);

                const CRElapsedMinutes = CRInitialCarbTime
                    ? Math.round((CREndTime.getTime() - CRInitialCarbTime.getTime()) / 1000 / 60)
                    : 0
                //console.error(CREndTime - CRInitialCarbTime, CRElapsedMinutes);
                if (CRElapsedMinutes < 60 || (i === 1 && mealCOB > 0)) {
                    console.error('Ignoring', CRElapsedMinutes, 'm CR period.')
                } else {
                    CRData.push(CRDatum)
                }

                CRCarbs = 0
                calculatingCR = false
            }
        }

        const glucoseDatum = {
            ...current,
            avgDelta,
            BGI,
            deviation,
            mealCarbs,
        }

        // If mealCOB is zero but all deviations since hitting COB=0 are positive, assign those data points to CSFGlucoseData
        // Once deviations go negative for at least one data point after COB=0, we can use the rest of the data to tune ISF or basals
        if (mealCOB > 0 || absorbing || mealCarbs > 0) {
            // if meal IOB has decayed, then end absorption after this data point unless COB > 0
            if (iob.iob < currentBasal / 2) {
                absorbing = 0
                // otherwise, as long as deviations are positive, keep tracking carb deviations
            } else if (deviation > 0) {
                absorbing = 1
            } else {
                absorbing = 0
            }
            if (!absorbing && !mealCOB) {
                mealCarbs = 0
            }
            // check previous "type" value, and if it wasn't csf, set a mealAbsorption start flag
            //console.error(type);
            let mealAbsorption
            if (type !== 'csf') {
                mealAbsorption = 'start'
                console.error('start', 'carb absorption')
            }
            type = 'csf'
            //if (i == 0) { glucoseDatum.mealAbsorption = "end"; }
            CSFGlucoseData.push({
                ...glucoseDatum,
                mealCarbs,
                mealAbsorption,
            })
        } else {
            // check previous "type" value, and if it was csf, set a mealAbsorption end flag
            if (type === 'csf') {
                CSFGlucoseData[CSFGlucoseData.length - 1].mealAbsorption = 'end'
                console.error(CSFGlucoseData[CSFGlucoseData.length - 1].mealAbsorption, 'carb absorption')
            }

            if (iob.iob > 2 * currentBasal || deviation > 6 || uam) {
                if (deviation > 0) {
                    uam = 1
                } else {
                    uam = 0
                }
                let uamAbsorption
                if (type !== 'uam') {
                    uamAbsorption = 'start'
                    console.error('start', 'uannnounced meal absorption')
                }
                type = 'uam'
                UAMGlucoseData.push({
                    ...glucoseDatum,
                    uamAbsorption,
                })
            } else {
                if (type === 'uam') {
                    console.error('end unannounced meal absorption')
                }

                // Go through the remaining time periods and divide them into periods where scheduled basal insulin activity dominates. This would be determined by calculating the BG impact of scheduled basal insulin (for example 1U/hr * 48 mg/dL/U ISF = 48 mg/dL/hr = 5 mg/dL/5m), and comparing that to BGI from bolus and net basal insulin activity.
                // When BGI is positive (insulin activity is negative), we want to use that data to tune basals
                // When BGI is smaller than about 1/4 of basalBGI, we want to use that data to tune basals
                // When BGI is negative and more than about 1/4 of basalBGI, we can use that data to tune ISF,
                // unless avgDelta is positive: then that's some sort of unexplained rise we don't want to use for ISF, so that means basals
                if (basalBGI > -4 * BGI) {
                    type = 'basal'
                    basalGlucoseData.push(glucoseDatum)
                } else {
                    if (avgDelta > 0 && avgDelta > -2 * BGI) {
                        //type="unknown"
                        type = 'basal'
                        basalGlucoseData.push(glucoseDatum)
                    } else {
                        type = 'ISF'
                        ISFGlucoseData.push(glucoseDatum)
                    }
                }
            }
        }
        // debug line to print out all the things
        // get the time in HH:MM:SS
        const BGDateArray = BGDate.toString().split(' ')
        const BGTimeString = BGDateArray[4]
        // console.error(absorbing.toString(),"mealCOB:",mealCOB.toFixed(1),"mealCarbs:",mealCarbs,"basalBGI:",basalBGI.toFixed(1),"BGI:",BGI.toFixed(1),"IOB:",iob.iob.toFixed(1),"at",BGTime,"dev:",deviation,"avgDelta:",avgDelta,type);
        console.error(
            absorbing.toString(),
            'mealCOB:',
            mealCOB.toFixed(1),
            'mealCarbs:',
            mealCarbs,
            'BGI:',
            BGI.toFixed(1),
            'IOB:',
            iob.iob.toFixed(1),
            'at',
            BGTimeString,
            'dev:',
            dev5m,
            'avgDev:',
            deviation,
            'avgDelta:',
            avgDelta,
            type,
            BG,
            myCarbs
        )
    }

    const insulinTreatments = findInsulin({
        profile,
        history: opts.pumpHistory,
    })
    CRData = CRData.map(CRDatum => ({
        ...CRDatum,
        CRInsulin: insulinDosed({
            treatments: insulinTreatments,
            start: CRDatum.CRInitialCarbTime!,
            end: CRDatum.CREndTime,
        }),
    }))

    const CSFLength = CSFGlucoseData.length
    let ISFLength = ISFGlucoseData.length
    const UAMLength = UAMGlucoseData.length
    let basalLength = basalGlucoseData.length

    if (opts.categorize_uam_as_basal) {
        console.error('--categorize-uam-as-basal=true set: categorizing all UAM data as basal.')
        basalGlucoseData = basalGlucoseData.concat(UAMGlucoseData)
    } else if (CSFLength > 12) {
        console.error(
            'Found at least 1h of carb absorption: assuming all meals were announced, and categorizing UAM data as basal.'
        )
        basalGlucoseData = basalGlucoseData.concat(UAMGlucoseData)
    } else {
        if (2 * basalLength < UAMLength) {
            //console.error(basalGlucoseData, UAMGlucoseData);
            console.error('Warning: too many deviations categorized as UnAnnounced Meals')
            console.error('Adding', UAMLength, 'UAM deviations to', basalLength, 'basal ones')
            basalGlucoseData = basalGlucoseData.concat(UAMGlucoseData)
            //console.error(basalGlucoseData);
            // if too much data is excluded as UAM, add in the UAM deviations to basal, but then discard the highest 50%
            basalGlucoseData.sort((a, b) => {
                return a.deviation - b.deviation
            })
            basalGlucoseData = basalGlucoseData.slice(0, basalGlucoseData.length / 2)
            //console.error(newBasalGlucose);
            console.error('and selecting the lowest 50%, leaving', basalGlucoseData.length, 'basal+UAM ones')
        }

        if (2 * ISFLength < UAMLength && ISFLength < 10) {
            console.error('Adding', UAMLength, 'UAM deviations to', ISFLength, 'ISF ones')
            ISFGlucoseData = ISFGlucoseData.concat(UAMGlucoseData)
            // if too much data is excluded as UAM, add in the UAM deviations to ISF, but then discard the highest 50%
            ISFGlucoseData.sort((a, b) => {
                return a.deviation - b.deviation
            })
            ISFGlucoseData = ISFGlucoseData.slice(0, ISFGlucoseData.length / 2)
            //console.error(newISFGlucose);
            console.error('and selecting the lowest 50%, leaving', ISFGlucoseData.length, 'ISF+UAM ones')
            //console.error(ISFGlucoseData.length, UAMLength);
        }
    }
    basalLength = basalGlucoseData.length
    ISFLength = ISFGlucoseData.length
    if (4 * basalLength + ISFLength < CSFLength && ISFLength < 10) {
        console.error('Warning: too many deviations categorized as meals')
        //console.error("Adding",CSFLength,"CSF deviations to",basalLength,"basal ones");
        //var basalGlucoseData = basalGlucoseData.concat(CSFGlucoseData);
        console.error('Adding', CSFLength, 'CSF deviations to', ISFLength, 'ISF ones')
        ISFGlucoseData = [...ISFGlucoseData, ...CSFGlucoseData]
        CSFGlucoseData = []
    }

    return {
        CRData: CRData,
        CSFGlucoseData: CSFGlucoseData,
        ISFGlucoseData: ISFGlucoseData,
        basalGlucoseData: basalGlucoseData,
    }
}

export default categorizeBGDatums
