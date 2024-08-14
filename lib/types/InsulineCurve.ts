import { Schema } from '@effect/schema'

export const InsulineCurve = Schema.Literal('bilinear', 'rapid-acting', 'ultra-rapid').annotations({
    identifier: 'InsulineCurve',
    title: 'Insuline Curve',
})

/**
 * Insulin curve.
 *
 * - `ultra-rapid`: Fiasp
 * - `rapid-acting`: Humalog
 * - `bilinear`: old curve
 */
export type InsulineCurve = typeof InsulineCurve.Type
