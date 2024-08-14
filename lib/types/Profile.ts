import { Schema } from '@effect/schema'
import { constant } from 'effect/Function'
import { BasalSchedule } from './BasalSchedule'
import { CarbRatios } from './CarbRatios'
import { GlucoseUnit } from './GlucoseUnit'
import { ISFSensitivity } from './ISFSensitivity'
import { InsulineCurve } from './InsulineCurve'

export const ISFProfile = Schema.Struct({
    sensitivities: Schema.Array(ISFSensitivity),
    units: Schema.optional(Schema.String),
    user_preferred_units: Schema.optional(Schema.String),
})

export type ISFProfile = typeof ISFProfile.Type

export const ProfileDefaults = /*#__PURE__*/ Schema.Struct({
    max_iob: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 0,
    }),
    max_daily_safety_multiplier: Schema.optionalWith(Schema.Number, {
        nullable: true,
        default: constant(3),
    }),
    current_basal_safety_multiplier: Schema.optionalWith(Schema.Number, {
        nullable: true,
        default: constant(4),
    }),
    autosens_max: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 1.2,
    }),
    autosens_min: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 0.7,
    }),
    rewind_resets_autosens: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(true),
    }),
    high_temptarget_raises_sensitivity: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(false),
    }),
    low_temptarget_lowers_sensitivity: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(false),
    }),
    sensitivity_raises_target: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(true),
    }),
    resistance_lowers_target: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(false),
    }),
    exercise_mode: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    half_basal_exercise_target: Schema.optionalWith(Schema.Number, {
        nullable: true,
        default: constant(160),
    }),
    maxCOB: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(120) }),
    skip_neutral_temps: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    unsuspend_if_no_temp: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(false),
    }),
    bolussnooze_dia_divisor: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThan(0)), {
        nullable: true,
        default: constant(2),
    }),
    min_5m_carbimpact: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 8,
    }),
    autotune_isf_adjustmentFraction: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 1.0,
    }),
    remainingCarbsFraction: Schema.optionalWith(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 1.0,
    }),
    remainingCarbsCap: Schema.optionalWith(Schema.Int.pipe(Schema.greaterThanOrEqualTo(0)), {
        nullable: true,
        default: () => 90,
    }),
    enableUAM: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(true) }),
    A52_risk_enable: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    enableSMB_with_COB: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    enableSMB_with_temptarget: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(false),
    }),

    enableSMB_always: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    enableSMB_after_carbs: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(false),
    }),
    enableSMB_high_bg: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    enableSMB_high_bg_target: Schema.optionalWith(Schema.Number, {
        nullable: true,
        default: constant(110),
    }),
    allowSMB_with_high_temptarget: Schema.optionalWith(Schema.Boolean, {
        nullable: true,
        default: constant(false),
    }),
    maxSMBBasalMinutes: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(30) }),
    maxUAMSMBBasalMinutes: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(30) }),
    SMBInterval: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(3) }),
    bolus_increment: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(0.1) }),
    maxDelta_bg_threshold: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(0.2) }),
    curve: Schema.optionalWith(InsulineCurve, {
        nullable: true,
        default: constant('rapid-acting' as const),
    }),
    useCustomPeakTime: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    insulinPeakTime: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(75) }),
    carbsReqThreshold: Schema.optionalWith(Schema.Number, { nullable: true, default: constant(1) }),
    offline_hotspot: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    noisyCGMTargetMultiplier: Schema.optionalWith(Schema.Number, {
        nullable: true,
        default: constant(1.3),
    }),
    suspend_zeros_iob: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(true) }),
    enableEnliteBgproxy: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    calc_glucose_noise: Schema.optionalWith(Schema.Boolean, { nullable: true, default: constant(false) }),
    target_bg: Schema.optionalWith(
        Schema.Union(Schema.Literal(false), Schema.Int.pipe(Schema.greaterThanOrEqualTo(0))),
        {
            nullable: true,
            default: constant(false as const),
        }
    ),
    edison_battery_shutdown_voltage: Schema.optionalWith(Schema.Number, {
        nullable: true,
        default: constant(3050),
    }),
    pi_battery_shutdown_percent: Schema.optionalWith(Schema.Number, {
        nullable: true,
        default: constant(2),
    }),
    model: Schema.optionalWith(Schema.Union(Schema.NonEmptyString, Schema.Int), { nullable: true }),
})

export interface ProfileDefaults extends Schema.Schema.Type<typeof ProfileDefaults> {}

export const Profile = Schema.Struct({
    ...ProfileDefaults.fields,
    basalprofile: Schema.Array(BasalSchedule),
    current_basal: Schema.Number.pipe(Schema.greaterThan(0)),
    sens: Schema.Number.pipe(Schema.greaterThanOrEqualTo(5)),
    carb_ratio: Schema.optional(Schema.Number),
    carb_ratios: Schema.optional(CarbRatios),
    out_units: Schema.optional(GlucoseUnit),
    dia: Schema.Number.pipe(Schema.greaterThan(1)),
    max_daily_basal: Schema.Number.pipe(Schema.greaterThan(0)),
    max_basal: Schema.optional(Schema.Number.pipe(Schema.greaterThanOrEqualTo(0.1))),
    min_bg: Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)),
    max_bg: Schema.Number.pipe(Schema.greaterThanOrEqualTo(0)),
    temptargetSet: Schema.optionalWith(Schema.Boolean, { nullable: true }),
    bg_targets: Schema.optionalWith(Schema.Unknown, { nullable: true }),
    isfProfile: Schema.optionalWith(ISFProfile, { nullable: true }),
})

export interface Profile extends Schema.Schema.Type<typeof Profile> {}
