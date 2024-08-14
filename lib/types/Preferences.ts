import { Schema } from '@effect/schema'

import { constant } from 'effect/Function'
import { BasalSchedule } from './BasalSchedule'
import { CarbRatios } from './CarbRatios'
import { GlucoseUnit } from './GlucoseUnit'
import { InsulineCurve } from './InsulineCurve'
import { ISFProfile } from './Profile'
import { ScheduleStart } from './ScheduleStart'
import { TempTarget } from './TempTarget'

const PumpSettings = Schema.Struct({
    // maxBolus: Schema.Number,
    maxBasal: Schema.optional(Schema.Number),
    insulin_action_curve: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThan(1)), {
        default: constant(2),
    }),
}).annotations({
    identifier: 'PumpSettings',
    title: 'Pump Settings',
})

type PumpSettings = typeof PumpSettings.Type

const BGTarget = Schema.Struct({
    offset: Schema.Number,
    start: Schema.optionalWith(ScheduleStart, { exact: true }),
    low: Schema.Number,
    high: Schema.Number,
})

export type BgTarget = typeof BGTarget.Type

const Targets = Schema.Struct({
    user_preferred_units: Schema.optional(GlucoseUnit),
    targets: Schema.NonEmptyArray(BGTarget),
})

type Targets = typeof Targets.Type

const Basals = Schema.NonEmptyArray(BasalSchedule)
type Basals = typeof Basals.Type

export const Preferences = /*#__PURE__*/ Schema.Struct({
    max_iob: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 0,
    }),
    max_daily_safety_multiplier: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(3),
    }),
    current_basal_safety_multiplier: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(4),
    }),
    autosens_max: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(1.2),
    }),
    autosens_min: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(0.7),
    }),
    rewind_resets_autosens: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => true }),
    high_temptarget_raises_sensitivity: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: () => false,
    }),
    low_temptarget_lowers_sensitivity: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: () => false,
    }),
    sensitivity_raises_target: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: () => true,
    }),
    resistance_lowers_target: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: () => false,
    }),
    exercise_mode: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    half_basal_exercise_target: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 160,
    }),
    maxCOB: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 120,
    }),
    skip_neutral_temps: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    unsuspend_if_no_temp: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    bolussnooze_dia_divisor: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 2,
    }),
    min_5m_carbimpact: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 8,
    }),
    autotune_isf_adjustmentFraction: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(1.0),
    }),
    remainingCarbsFraction: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(1.0),
    }),
    remainingCarbsCap: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 90,
    }),
    enableUAM: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => true }),
    A52_risk_enable: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    enableSMB_with_COB: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    enableSMB_with_temptarget: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: () => false,
    }),
    enableSMB_always: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    enableSMB_after_carbs: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    enableSMB_high_bg: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    enableSMB_high_bg_target: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 110,
    }),
    allowSMB_with_high_temptarget: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: () => false,
    }),
    maxSMBBasalMinutes: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 30,
    }),
    maxUAMSMBBasalMinutes: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 30,
    }),
    SMBInterval: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 3,
    }),
    bolus_increment: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(0.1),
    }),
    maxDelta_bg_threshold: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(0.2),
    }),
    curve: Schema.optionalWith(InsulineCurve, { nullable: true, default: () => 'rapid-acting' as const }),
    useCustomPeakTime: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    insulinPeakTime: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 75,
    }),
    carbsReqThreshold: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 1,
    }),
    offline_hotspot: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    noisyCGMTargetMultiplier: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: constant(1.3),
    }),
    suspend_zeros_iob: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => true }),
    enableEnliteBgproxy: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    calc_glucose_noise: Schema.optionalWith(Schema.Boolean, { nullable: true, default: () => false }),
    target_bg: Schema.optionalWith(
        Schema.Union(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), Schema.Literal(false)),
        {
            nullable: true,
            default: () => false as const,
        }
    ),
    edison_battery_shutdown_voltage: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 3050,
    }),
    pi_battery_shutdown_percent: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 2,
    }),
    isf: ISFProfile,
    // no defaults
    basals: Basals,
    settings: PumpSettings,
    targets: Targets,
    temptargets: Schema.Array(TempTarget),
    // @todo: can we make it just a string?
    model: Schema.optionalWith(Schema.Union(Schema.NonEmptyString, Schema.Int), { nullable: true }),
    carbratio: Schema.optionalWith(CarbRatios, { strict: true, nullable: true }),
}).annotations({
    identifier: 'Preferences',
    title: 'Preferences',
})

//export interface Preferences extends Schema.Schema.Type<typeof Preferences> {}

export interface Preferences extends Schema.Schema.Type<typeof Preferences> {
    max_iob: number
    max_daily_safety_multiplier: number
    current_basal_safety_multiplier: number
    autosens_max: number
    autosens_min: number
    rewind_resets_autosens: boolean
    /** raise sensitivity for temptargets >= 101.  synonym for exercise_mode */
    high_temptarget_raises_sensitivity: boolean
    /** lower sensitivity for temptargets <= 99. */
    low_temptarget_lowers_sensitivity: boolean
    /** raise BG target when autosens detects sensitivity */
    sensitivity_raises_target: boolean
    /** lower BG target when autosens detects resistance */
    resistance_lowers_target: boolean
    /** when true, > 100 mg/dL high temp target adjusts sensitivityRatio for exercise_mode. This majorly changes the behavior of high temp targets from before. synonmym for high_temptarget_raises_sensitivity */
    exercise_mode: boolean
    half_basal_exercise_target: number
    /**
     * Max carbs absorbed in 4 hours.
     *
     * Default to 120 because that's the most a typical body can absorb over 4 hours.
     *
     * If someone enters more carbs or stacks more; OpenAPS will just truncate dosing based on 120.
     * Essentially, this just limits AMA/SMB as a safety cap against excessive COB entry.
     */
    maxCOB: number
    /** if true, don't set neutral temps */
    skip_neutral_temps: boolean
    /** if true, pump will un-suspend after a zero temp finishes */
    unsuspend_if_no_temp: boolean
    /** bolus snooze decays after 1/2 of DIA */
    bolussnooze_dia_divisor: number
    /** mg/dL per 5m (8 mg/dL/5m corresponds to 24g/hr at a CSF of 4 mg/dL/g (x/5*60/4)) */
    min_5m_carbimpact: number
    /** keep autotune ISF closer to pump ISF via a weighted average of fullNewISF and pumpISF.  1.0 allows full adjustment, 0 is no adjustment from pump ISF. */
    autotune_isf_adjustmentFraction: number
    /** fraction of carbs we'll assume will absorb over 4h if we don't yet see carb absorption */
    remainingCarbsFraction: number
    /** max carbs we'll assume will absorb over 4h if we don't yet see carb absorption */
    remainingCarbsCap: number
    /** Enable detection of unannounced meal carb absorption */
    enableUAM: boolean
    A52_risk_enable: boolean
    /** Enable supermicrobolus while COB is positive */
    enableSMB_with_COB: boolean
    /** Enable supermicrobolus for eating soon temp targets */
    enableSMB_with_temptarget: boolean
    /**
     * Always enable supermicrobolus (unless disabled by high temptarget).
     *
     * **WARNING**
     * DO NOT USE enableSMB_always or enableSMB_after_carbs with Libre or similar
     *
     * LimiTTer, etc. do not properly filter out high-noise SGVs.  xDrip+ builds greater than or equal to
     * version number d8e-7097-2018-01-22 provide proper noise values, so that oref0 can ignore high noise
     * readings, and can temporarily raise the BG target when sensor readings have medium noise,
     * resulting in appropriate SMB behaviour.  Older versions of xDrip+ should not be used with enableSMB_always.
     * Using SMB overnight with such data sources risks causing a dangerous overdose of insulin
     * if the CGM sensor reads falsely high and doesn't come down as actual BG does
     */
    enableSMB_always: boolean
    /**
     * Enable supermicrobolus for 6h after carbs, even with 0 COB.
     *
     * **WARNING**
     * DO NOT USE enableSMB_always or enableSMB_after_carbs with Libre or similar.
     */
    enableSMB_after_carbs: boolean
    /** Enable SMBs when a high BG is detected, based on the high BG target (adjusted or profile) */
    enableSMB_high_bg: boolean
    /** Set the value enableSMB_high_bg will compare against to enable SMB. If BG > than this value, SMBs should enable. */
    enableSMB_high_bg_target: number
    /** Allow supermicrobolus (if otherwise enabled) even with high temp targets */
    allowSMB_with_high_temptarget: boolean
    /** maximum minutes of basal that can be delivered as a single SMB with uncovered COB */
    maxSMBBasalMinutes: number
    /** maximum minutes of basal that can be delivered as a single SMB when IOB exceeds COB */
    maxUAMSMBBasalMinutes: number
    /** minimum interval between SMBs, in minutes. */
    SMBInterval: number
    /** minimum bolus that can be delivered as an SMB */
    bolus_increment: number
    /** maximum change in bg to use SMB, above that will disable SMB */
    maxDelta_bg_threshold: number
    /** Insulin curve. */
    curve: InsulineCurve
    /** allows changing insulinPeakTime */
    useCustomPeakTime: boolean
    /**
     * Number of minutes after a bolus activity peaks.
     * Defaults to 55m for Fiasp if useCustomPeakTime: boolean
     */
    insulinPeakTime: number
    /** grams of carbsReq to trigger a pushover */
    carbsReqThreshold: number
    /** enabled an offline-only local wifi hotspot if no Internet available */
    offline_hotspot: boolean
    /** increase target by this amount when looping off raw/noisy CGM data */
    noisyCGMTargetMultiplier: number
    /** recognize pump suspends as non insulin delivery events */
    suspend_zeros_iob: boolean
    /**
     * Send the glucose data to the pump emulating an enlite sensor.
     * This allows to setup high / low warnings when offline and see trend.
     *
     * To enable this feature, enable the sensor, set a sensor with id 0000000,
     * go to start sensor and press find lost sensor.
     */
    enableEnliteBgproxy: boolean
    calc_glucose_noise: boolean
    /** set to an integer value in mg/dL to override pump min_bg */
    target_bg: number | false
}

/**
 * {
    "max_iob": 14,
    "max_daily_safety_multiplier": 3,
    "current_basal_safety_multiplier": 4,
    "autosens_max": 1.3,
    "autosens_min": 0.7,
    "rewind_resets_autosens": true,
    "high_temptarget_raises_sensitivity": true,
    "low_temptarget_lowers_sensitivity": true,
    "sensitivity_raises_target": true,
    "resistance_lowers_target": false,
    "exercise_mode": false,
    "half_basal_exercise_target": 160,
    "maxCOB": 120,
    "skip_neutral_temps": false,
    "unsuspend_if_no_temp": false,
    "min_5m_carbimpact": 8,
    "autotune_isf_adjustmentFraction": 1,
    "remainingCarbsFraction": 1,
    "remainingCarbsCap": 90,
    "enableUAM": true,
    "A52_risk_enable": false,
    "enableSMB_with_COB": true,
    "enableSMB_with_temptarget": true,
    "enableSMB_always": false,
    "enableSMB_after_carbs": true,
    "allowSMB_with_high_temptarget": false,
    "maxSMBBasalMinutes": 90,
    "maxUAMSMBBasalMinutes": 120,
    "SMBInterval": 3,
    "bolus_increment": 0.05,
    "maxDelta_bg_threshold": 0.2,
    "curve": "ultra-rapid",
    "useCustomPeakTime": false,
    "insulinPeakTime": 55,
    "carbsReqThreshold": 1,
    "offline_hotspot": false,
    "noisyCGMTargetMultiplier": 1.3,
    "suspend_zeros_iob": false,
    "enableEnliteBgproxy": false,
    "calc_glucose_noise": false,
    "target_bg": false,
    "smb_delivery_ratio": 0.7,
    "adjustmentFactor": 0.7,
    "useNewFormula": true,
    "enableDynamicCR": true,
    "sigmoid": true,
    "weightPercentage": 0.65,
    "tddAdjBasal": true,
    "enableSMB_high_bg": true,
    "enableSMB_high_bg_target": 110,
    "threshold_setting": 65,
    "dia": 9,
    "model": "722",
    "current_basal": 0.7,
    "basalprofile": [
        {
            "rate": 0.7,
            "start": "00:00:00",
            "minutes": 0
        },
        {
            "rate": 0.7,
            "minutes": 180,
            "start": "03:00:00"
        },
        {
            "start": "09:00:00",
            "minutes": 540,
            "rate": 0.7
        }
    ],
    "max_daily_basal": 0.7,
    "max_basal": 3,
    "out_units": "mg/dL",
    "min_bg": 98,
    "max_bg": 98,
    "bg_targets": {
        "units": "mg/dL",
        "user_preferred_units": "mg/dL",
        "targets": [
            {
                "start": "00:00:00",
                "high": 98,
                "offset": 0,
                "low": 98,
                "max_bg": 98,
                "min_bg": 98
            }
        ]
    },
    "sens": 65,
    "isfProfile": {
        "user_preferred_units": "mg/dL",
        "units": "mg/dL",
        "sensitivities": [
            {
                "start": "00:00:00",
                "sensitivity": 65,
                "offset": 0,
                "endOffset": 1440
            }
        ]
    },
    "carb_ratio": 6.5,
    "carb_ratios": {
        "units": "grams",
        "schedule": [
            {
                "start": "00:00:00",
                "offset": 0,
                "ratio": 6
            },
            {
                "ratio": 5,
                "start": "08:30:00",
                "offset": 510
            },
            {
                "start": "11:30:00",
                "ratio": 6,
                "offset": 690
            },
            {
                "offset": 960,
                "ratio": 6.5,
                "start": "16:00:00"
            }
        ]
    }
}
 */
