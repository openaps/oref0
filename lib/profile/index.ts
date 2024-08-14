import type { FinalResult } from '../bin/utils'
import { console_error } from '../bin/utils'
import type { BasalSchedule } from '../types/BasalSchedule'
import type { Preferences } from '../types/Preferences'
import { maxDailyBasal, basalLookup, maxBasalLookup } from './basal'
//import { carbRatioLookup } from './carbs'
import { carbRatioLookup } from './carbs'
import { isfLookup } from './isf'
import * as targets from './targets'

export function defaults() {
    return /* profile */ {
        max_iob: 0, // if max_iob is not provided, will default to zero
        max_daily_safety_multiplier: 3,
        current_basal_safety_multiplier: 4,
        autosens_max: 1.2,
        autosens_min: 0.7,
        rewind_resets_autosens: true, // reset autosensitivity to neutral for awhile after each pump rewind
        // , autosens_adjust_targets: false // when autosens detects sensitivity/resistance, also adjust BG target accordingly
        high_temptarget_raises_sensitivity: false, // raise sensitivity for temptargets >= 101.  synonym for exercise_mode
        low_temptarget_lowers_sensitivity: false, // lower sensitivity for temptargets <= 99.
        sensitivity_raises_target: true, // raise BG target when autosens detects sensitivity
        resistance_lowers_target: false, // lower BG target when autosens detects resistance
        exercise_mode: false, // when true, > 100 mg/dL high temp target adjusts sensitivityRatio for exercise_mode. This majorly changes the behavior of high temp targets from before. synonmym for high_temptarget_raises_sensitivity
        half_basal_exercise_target: 160, // when temptarget is 160 mg/dL *and* exercise_mode=true, run 50% basal at this level (120 = 75%; 140 = 60%)
        // create maxCOB and default it to 120 because that's the most a typical body can absorb over 4 hours.
        // (If someone enters more carbs or stacks more; OpenAPS will just truncate dosing based on 120.
        // Essentially, this just limits AMA/SMB as a safety cap against excessive COB entry)
        maxCOB: 120,
        skip_neutral_temps: false, // if true, don't set neutral temps
        unsuspend_if_no_temp: false, // if true, pump will un-suspend after a zero temp finishes
        bolussnooze_dia_divisor: 2, // bolus snooze decays after 1/2 of DIA
        min_5m_carbimpact: 8, // mg/dL per 5m (8 mg/dL/5m corresponds to 24g/hr at a CSF of 4 mg/dL/g (x/5*60/4))
        autotune_isf_adjustmentFraction: 1.0, // keep autotune ISF closer to pump ISF via a weighted average of fullNewISF and pumpISF.  1.0 allows full adjustment, 0 is no adjustment from pump ISF.
        remainingCarbsFraction: 1.0, // fraction of carbs we'll assume will absorb over 4h if we don't yet see carb absorption
        remainingCarbsCap: 90, // max carbs we'll assume will absorb over 4h if we don't yet see carb absorption
        // WARNING: use SMB with caution: it can and will automatically bolus up to max_iob worth of extra insulin
        enableUAM: true, // enable detection of unannounced meal carb absorption
        A52_risk_enable: false,
        enableSMB_with_COB: false, // enable supermicrobolus while COB is positive
        enableSMB_with_temptarget: false, // enable supermicrobolus for eating soon temp targets
        // *** WARNING *** DO NOT USE enableSMB_always or enableSMB_after_carbs with Libre or similar
        // LimiTTer, etc. do not properly filter out high-noise SGVs.  xDrip+ builds greater than or equal to
        // version number d8e-7097-2018-01-22 provide proper noise values, so that oref0 can ignore high noise
        // readings, and can temporarily raise the BG target when sensor readings have medium noise,
        // resulting in appropriate SMB behaviour.  Older versions of xDrip+ should not be used with enableSMB_always.
        // Using SMB overnight with such data sources risks causing a dangerous overdose of insulin
        // if the CGM sensor reads falsely high and doesn't come down as actual BG does
        enableSMB_always: false, // always enable supermicrobolus (unless disabled by high temptarget)
        enableSMB_after_carbs: false, // enable supermicrobolus for 6h after carbs, even with 0 COB
        enableSMB_high_bg: false, // enable SMBs when a high BG is detected, based on the high BG target (adjusted or profile)
        enableSMB_high_bg_target: 110, // set the value enableSMB_high_bg will compare against to enable SMB. If BG > than this value, SMBs should enable.
        // *** WARNING *** DO NOT USE enableSMB_always or enableSMB_after_carbs with Libre or similar.
        allowSMB_with_high_temptarget: false, // allow supermicrobolus (if otherwise enabled) even with high temp targets
        maxSMBBasalMinutes: 30, // maximum minutes of basal that can be delivered as a single SMB with uncovered COB
        maxUAMSMBBasalMinutes: 30, // maximum minutes of basal that can be delivered as a single SMB when IOB exceeds COB
        SMBInterval: 3, // minimum interval between SMBs, in minutes.
        bolus_increment: 0.1, // minimum bolus that can be delivered as an SMB
        maxDelta_bg_threshold: 0.2, // maximum change in bg to use SMB, above that will disable SMB
        curve: 'rapid-acting', // change this to "ultra-rapid" for Fiasp, or "bilinear" for old curve
        useCustomPeakTime: false, // allows changing insulinPeakTime
        insulinPeakTime: 75, // number of minutes after a bolus activity peaks.  defaults to 55m for Fiasp if useCustomPeakTime: false
        carbsReqThreshold: 1, // grams of carbsReq to trigger a pushover
        offline_hotspot: false, // enabled an offline-only local wifi hotspot if no Internet available
        noisyCGMTargetMultiplier: 1.3, // increase target by this amount when looping off raw/noisy CGM data
        suspend_zeros_iob: true, // recognize pump suspends as non insulin delivery events
        // send the glucose data to the pump emulating an enlite sensor. This allows to setup high / low warnings when offline and see trend.
        // To enable this feature, enable the sensor, set a sensor with id 0000000, go to start sensor and press find lost sensor.
        enableEnliteBgproxy: false,
        // TODO: make maxRaw a preference here usable by oref0-raw in myopenaps-cgm-loop
        //, maxRaw: 200 // highest raw/noisy CGM value considered safe to use for looping
        calc_glucose_noise: false,
        target_bg: false, // set to an integer value in mg/dL to override pump min_bg
        edison_battery_shutdown_voltage: 3050,
        pi_battery_shutdown_percent: 2,
    }
}

export function displayedDefaults(final_result: FinalResult) {
    const allDefaults = defaults()
    const profile = {
        max_iob: allDefaults.max_iob,
        max_daily_safety_multiplier: allDefaults.max_daily_safety_multiplier,
        current_basal_safety_multiplier: allDefaults.current_basal_safety_multiplier,
        autosens_max: allDefaults.autosens_max,
        autosens_min: allDefaults.autosens_min,
        rewind_resets_autosens: allDefaults.rewind_resets_autosens,
        exercise_mode: allDefaults.exercise_mode,
        sensitivity_raises_target: allDefaults.sensitivity_raises_target,
        unsuspend_if_no_temp: allDefaults.unsuspend_if_no_temp,
        enableSMB_with_COB: allDefaults.enableSMB_with_COB,
        enableSMB_with_temptarget: allDefaults.enableSMB_with_temptarget,
        enableUAM: allDefaults.enableUAM,
        curve: allDefaults.curve,
        offline_hotspot: allDefaults.offline_hotspot,
        edison_battery_shutdown_voltage: allDefaults.edison_battery_shutdown_voltage,
        pi_battery_shutdown_percent: allDefaults.pi_battery_shutdown_percent,
    }

    console_error(final_result, profile)
    return profile
}

function generate(final_result: FinalResult, inputs: Preferences, opts?: any) {
    const profile = opts && opts.type ? opts : defaults()
    const preferences = inputs

    // check if preferences has overrides for any of the default prefs
    // and apply if applicable
    for (const pref in profile) {
        if (Object.prototype.hasOwnProperty.call(preferences, pref)) {
            profile[pref] = (preferences as any)[pref]
        }
    }

    const pumpsettings_data = preferences.settings
    if (preferences.settings.insulin_action_curve > 1) {
        profile.dia = pumpsettings_data.insulin_action_curve
    } else {
        console_error(final_result, 'DIA of', profile.dia, 'is not supported')
        return -1
    }

    if (preferences.model) {
        profile.model = preferences.model
    }
    profile.skip_neutral_temps = preferences.skip_neutral_temps

    // try-catch just to fix test. Basal should be validated from the beginning
    try {
        profile.current_basal = basalLookup(preferences.basals)
    } catch (e) {
        console_error(final_result, String(e))
        return -1
    }
    if (!profile.current_basal) {
        console.error('ERROR: bad basal schedule', profile.current_basal)
        return -1
    }
    profile.basalprofile = preferences.basals.map((basalentry: BasalSchedule) => ({
        ...basalentry,
        rate: Math.round(basalentry.rate * 1000) / 1000,
    }))

    profile.max_daily_basal = maxDailyBasal(preferences)
    profile.max_basal = maxBasalLookup(preferences)

    if (profile.current_basal === 0) {
        console_error(final_result, 'current_basal of', profile.current_basal, 'is not supported')
        return -1
    }
    if (profile.max_daily_basal === 0) {
        console_error(final_result, 'max_daily_basal of', profile.max_daily_basal, 'is not supported')
        return -1
    }
    if (profile.max_basal < 0.1) {
        console_error(final_result, 'max_basal of', profile.max_basal, 'is not supported')
        return -1
    }

    const range = targets.bgTargetsLookup(final_result, preferences)
    profile.out_units = preferences.targets.user_preferred_units
    profile.min_bg = Math.round(range.min_bg)
    profile.max_bg = Math.round(range.max_bg)
    profile.bg_targets = preferences.targets
    ;(profile.bg_targets.targets || []).forEach((bg_entry: any) => {
        bg_entry.high = Math.round(bg_entry.high)
        bg_entry.low = Math.round(bg_entry.low)
        bg_entry.min_bg = Math.round(bg_entry.min_bg)
        bg_entry.max_bg = Math.round(bg_entry.max_bg)
    })

    delete profile.bg_targets.raw

    profile.temptargetSet = range.temptargetSet
    const [sens] = isfLookup(preferences.isf, undefined, null)
    profile.sens = sens
    profile.isfProfile = preferences.isf
    if (profile.sens < 5) {
        console_error(final_result, 'ISF of', profile.sens, 'is not supported')
        return -1
    }
    if (typeof preferences.carbratio !== 'undefined') {
        profile.carb_ratio = carbRatioLookup(final_result, preferences)
        profile.carb_ratios = preferences.carbratio
    } else {
        console_error(final_result, "Profile wasn't given carb ratio data, cannot calculate carb_ratio")
    }

    return profile
}

export default generate
