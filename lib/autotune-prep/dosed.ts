import { isBolusTreatment, type InsulinTreatment } from '../iob/InsulinTreatment'

interface Input {
    treatments: ReadonlyArray<InsulinTreatment>
    start: Date
    end: Date
}

export function insulinDosed(opts: Input): { insulin?: number } {
    const start = opts.start.getTime()
    const end = opts.end.getTime()
    const treatments = opts.treatments
    if (!treatments) {
        console.error('No treatments to process.')
        return {}
    }

    const insulin = treatments.reduce(
        (b, a) => (isBolusTreatment(a) && a.date > start && a.date <= end ? b + a.insulin : b),
        0
    )

    return {
        insulin: Math.round(insulin * 1000) / 1000,
    }
}

export default insulinDosed
